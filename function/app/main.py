"""Read-only metadata acceptance entrypoint for one approved manifest action.

No action is registered in the production manifest and no hook is attached.
This handler uses only Workpeg's invocation context, performs metadata GETs
for the two canonical namespaces, and returns sanitized status flags. It does
not read rows or invoke any write method.
"""

from domain.workpeg_adapter import AdapterError, resolve_tables
from domain.workpeg_function_tables import FunctionTablesError, WorkpegFunctionTables


_UNVERIFIED = {
    "token_authorization": "unverified",
    "inventory": "incomplete",
    "peg_scope": "unverified",
    "business_scope": "unverified",
    "actor_presence": "unverified",
}


def _denied(**updates):
    result = dict(_UNVERIFIED)
    result["token_authorization"] = "denied"
    result.update(updates)
    return result


def _result(*, token_authorization, inventory, peg_scope="unverified",
            business_scope="unverified", actor_presence="unverified"):
    return {
        "token_authorization": token_authorization,
        "inventory": inventory,
        "peg_scope": peg_scope,
        "business_scope": business_scope,
        "actor_presence": actor_presence,
    }


def _failure(error, *, lists_authorized, actor_presence):
    code = getattr(error, "code", "")
    if code == "function_peg_scope_mismatch":
        return _denied(peg_scope="mismatch")
    if code == "function_business_scope_mismatch":
        return _denied(business_scope="mismatch")
    if lists_authorized:
        return _result(token_authorization="accepted", inventory="incomplete",
                       peg_scope="match", business_scope="match",
                       actor_presence=actor_presence)
    if getattr(error, "status", None) in (401, 403):
        return _denied()
    return dict(_UNVERIFIED)


def main(context: dict, payload: dict) -> dict:
    """Validate one invocation-scoped read-only inventory request.

    Workpeg supplies ``business``, ``token`` and ``phase``. It may also supply
    ``staff``; the current documented manifest-action envelope does not require
    it. The action payload must be empty and cannot override trusted context.
    This metadata-only check can confirm that Workpeg accepted the scoped
    token, but it cannot identify an actor when ``staff.email`` is absent. The
    owner must verify the selected Workpeg business before invoking.
    """
    if not isinstance(context, dict) or not isinstance(payload, dict) or payload:
        raise ValueError("invalid_workpeg_function_envelope")
    if context.get("phase") != "post_save_hook":
        raise RuntimeError("roomay_readonly_action_context_invalid")

    lists_authorized = False
    actor_presence = "unverified"
    try:
        business_id = context.get("business")
        tables = WorkpegFunctionTables(
            context, expected_business_id=business_id, require_actor=False)
        actor_presence = "verified" if tables.staff_email else "unverified"
        inventory = {
            "roomay_hotel_v1": tables.get_tables("roomay_hotel_v1"),
            "roomay_requests_v1": tables.get_tables("roomay_requests_v1"),
        }
        lists_authorized = True
        # This diagnostic only validates metadata. Do not manufacture an
        # actor-bound scope attestation when the action envelope has no actor.
        resolve_tables(inventory)
    except (FunctionTablesError, AdapterError) as error:
        return _failure(error, lists_authorized=lists_authorized,
                        actor_presence=actor_presence)
    except Exception:
        # Never reflect a token, actor identity, response or arbitrary error.
        if lists_authorized:
            return _result(token_authorization="accepted", inventory="incomplete",
                           peg_scope="match", business_scope="match",
                           actor_presence=actor_presence)
        return _denied()

    return _result(token_authorization="accepted", inventory="complete",
                   peg_scope="match", business_scope="match",
                   actor_presence=actor_presence)
