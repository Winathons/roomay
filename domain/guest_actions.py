"""Narrow offline guest action gateway shared by typed chat and Vapi adapters.

Only a message, confirmation, or cancellation can be submitted. Hotel scope is
resolved from a server-held guest session; arbitrary model tool names, record
IDs, roles, rooms, business IDs, and persistence operations are not accepted.
"""
from copy import deepcopy
from datetime import datetime, timezone
import secrets
import threading
from uuid import uuid4

from .conversation_intake import CHANNELS, handle_conversation_turn
from .guest_access import GuestSessionError, GuestSessionAuthority


OPERATIONS = frozenset({"message", "confirm", "cancel"})
MAX_SESSION_INTERACTIONS = 64


class GuestActionError(ValueError):
    """Safe fixed-code refusal from the guest-facing action boundary."""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


class GuestActionGateway:
    """Prepare service-request intents without submission or persistence.

    ``classifier_output`` and ``provider_status`` are trusted adapter inputs,
    never fields to forward directly from a guest or model tool call. The
    existing conversation-intake module validates classifier shape/routing.
    """

    def __init__(self, sessions: GuestSessionAuthority, *, clock=None,
                 confirmation_factory=None):
        if not isinstance(sessions, GuestSessionAuthority):
            raise TypeError("trusted guest session authority required")
        self.sessions = sessions
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.confirmation_factory = confirmation_factory or (lambda: secrets.token_urlsafe(24))

    @staticmethod
    def _public_result(state, message, *, handoff=False, proposal=None):
        result = {
            "state": state,
            "message": message,
            "handoff_required": handoff,
            "proposal": deepcopy(proposal),
            "submitted": False,
            "persisted": False,
        }
        return result

    def _at(self):
        value = self.clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise GuestActionError("trusted_clock_unavailable")
        return value.isoformat()

    def handle_guest_action(self, *, session_token, channel, operation,
                            interaction_id=None,
                            text=None, confirmation_handle=None,
                            classifier_output=None, provider_status="ok"):
        """Process exactly one allowlisted guest action through WOR-18.

        The transport adapter must derive ``channel`` and provider fields from
        its trusted server-side connection. It must not pass guest-supplied
        authorization claims or model-selected operations.
        """
        if not isinstance(channel, str) or channel not in CHANNELS:
            raise GuestActionError("unsupported_channel")
        if not isinstance(operation, str) or operation not in OPERATIONS:
            raise GuestActionError("unsupported_action")
        if operation == "message":
            if (not isinstance(text, str) or not text.strip() or len(text.strip()) > 1000
                    or confirmation_handle is not None
                    or not isinstance(interaction_id, str)
                    or not interaction_id.strip() or len(interaction_id) > 128):
                raise GuestActionError("invalid_message")
        elif (text is not None or classifier_output is not None or provider_status != "ok"
              or interaction_id is not None):
            raise GuestActionError("invalid_action_shape")
        try:
            record, grant = self.sessions.resolve_for_action(session_token)
        except GuestSessionError as error:
            raise GuestActionError(error.code) from None

        with record.action_lock:
            if operation == "message":
                normalized_text = text.strip()
                fingerprint = (channel, normalized_text)
                previous = record.interactions.get(interaction_id)
                if previous is not None:
                    if previous[0] != fingerprint:
                        raise GuestActionError("interaction_id_conflict")
                    cached = deepcopy(previous[1])
                    # Redelivery must never re-offer a confirmation superseded
                    # by a later message, even when the old message ID matches.
                    if cached["state"] == "awaiting_confirmation":
                        handle = (cached.get("proposal") or {}).get("handle")
                        pending = record.pending
                        if pending is None or pending["handle"] != handle:
                            return self._public_result(
                                "confirmation_expired",
                                "That earlier request is no longer awaiting confirmation. "
                                "Please review your latest request.",
                            )
                    return cached
                if len(record.interactions) >= MAX_SESSION_INTERACTIONS:
                    raise GuestActionError("interaction_capacity_reached")
                # A new message invalidates any previous unconfirmed proposal.
                record.pending = None
                record.completed = None
                at = self._at()
                turn_id = str(uuid4())
                try:
                    outcome = handle_conversation_turn(
                        normalized_text, channel=channel,
                        conversation_id=record.conversation_id, turn_id=turn_id,
                        at=at, confirmed=False,
                        classifier_output=deepcopy(classifier_output),
                        provider_status=provider_status,
                        access_context=grant.context, scope=grant.scope,
                    )
                except Exception:
                    return self._public_result(
                        "unavailable", "This request could not be safely prepared. Contact Reception.")
                if outcome.get("state") == "awaiting_confirmation":
                    intent = outcome.get("internal", {}).get("intent", {})
                    try:
                        handle = self.confirmation_factory()
                        if not isinstance(handle, str) or len(handle) < 24:
                            raise ValueError
                        record.pending = {
                            "handle": handle, "text": normalized_text, "channel": channel,
                            "turn_id": turn_id, "at": at,
                            "classifier_output": deepcopy(classifier_output),
                        }
                    except Exception:
                        return self._public_result(
                            "unavailable", "Confirmation could not be created. Contact Reception.")
                    proposal = {
                        "handle": handle,
                        "description": normalized_text,
                        "category": self._label(intent.get("category")),
                        "department": self._label(intent.get("department")),
                    }
                    result = self._public_result(
                        "awaiting_confirmation", outcome["message"], proposal=proposal)
                else:
                    result = self._public_result(
                        outcome.get("state", "unavailable"),
                        outcome.get("message", "This request is unavailable. Contact Reception."),
                        handoff=outcome.get("handoff_required") is True,
                    )
                record.interactions[interaction_id] = (fingerprint, deepcopy(result))
                return result

            pending = record.pending
            if (not isinstance(confirmation_handle, str) or pending is None
                    or not secrets.compare_digest(confirmation_handle, pending["handle"])):
                completed = record.completed
                if (operation == "confirm" and completed is not None
                        and isinstance(confirmation_handle, str)
                        and secrets.compare_digest(confirmation_handle, completed[0])):
                    return deepcopy(completed[1])
                raise GuestActionError("confirmation_invalid_or_expired")

            if operation == "cancel":
                record.pending = None
                result = self._public_result(
                    "cancelled", "Canceled. Nothing was prepared, sent, or saved.")
                record.completed = (pending["handle"], result)
                return deepcopy(result)

            try:
                outcome = handle_conversation_turn(
                    pending["text"], channel=pending["channel"],
                    conversation_id=record.conversation_id, turn_id=pending["turn_id"],
                    at=pending["at"], confirmed=True,
                    classifier_output=deepcopy(pending["classifier_output"]),
                    access_context=grant.context, scope=grant.scope,
                )
            except Exception:
                outcome = {"state": "unavailable",
                           "message": "This request could not be safely prepared. Contact Reception."}
            record.pending = None
            result = self._public_result(
                outcome.get("state", "unavailable"),
                outcome.get("message", "This request is unavailable. Contact Reception."),
                handoff=outcome.get("handoff_required") is True,
            )
            if outcome.get("state") == "prepared":
                intent = outcome.get("internal", {}).get("intent", {})
                result["proposal"] = {
                    "description": pending["text"],
                    "category": self._label(intent.get("category")),
                    "department": self._label(intent.get("department")),
                }
                result["message"] = (
                    "The request is prepared for staff review in this offline contract. "
                    "It has not been sent or saved; no ticket was created.")
            record.completed = (pending["handle"], deepcopy(result))
            return result

    @staticmethod
    def _label(value):
        if not isinstance(value, str) or not value:
            return "Reception"
        return value.replace("_", " ").title()
