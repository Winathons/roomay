"""Fail-closed resolution of approved hotel facts for AI-assisted answers.

This is a pure policy boundary. It does not fetch Workpeg data, authenticate a
caller, or make a response safe merely because a Python dataclass was created.
Production callers must build its inputs from a fresh, authenticated Workpeg
snapshot and a separately reviewed source-field allowlist. No current Roomay
table contract contains guest guidance facts, so no production source mapping
is configured by this module.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum

from .access_control import (
    AccessContext, AccessDenied, authorize_access, authorize_hotel_snapshot,
)
from .hotel import validate_snapshot


MAX_FACT_AGE = timedelta(minutes=5)
MAX_FACT_TEXT = 1200
FACT_UNAVAILABLE_MESSAGE = (
    "I don't have verified information for that yet. Please contact Reception."
)


class FactTopic(str, Enum):
    WIFI = "wifi"
    AIR_CONDITIONER = "air_conditioner"
    TELEVISION = "television"
    HOTEL_POLICY = "hotel_policy"
    RECEPTION_CONTACT = "reception_contact"


class FactScope(str, Enum):
    HOTEL = "hotel"
    ROOM = "room"


@dataclass(frozen=True)
class FactSourcePolicy:
    """Server-owned mapping from an answer topic to one approved Workpeg field.

    This mapping must come from a reviewed Workpeg table contract, never from
    a model, URL, browser payload, or guest message. ``field_id`` is a schema
    column ID/name; it is not an arbitrary prompt or query expression.
    """

    namespace: str
    table: str
    field_id: str
    scope: FactScope


@dataclass(frozen=True)
class HotelFactRecord:
    """Normalized fact from one independently validated Workpeg row.

    Identifiers and source metadata are internal input only and are never
    copied into the guest-facing result. ``value`` is returned verbatim; an AI
    provider must not embellish it with unsupported details.
    """

    topic: FactTopic
    value: str
    business_id: str
    hotel_id: str
    scope: FactScope
    observed_at: str
    source_namespace: str
    source_table: str
    source_field: str
    room_id: str | None = None


@dataclass(frozen=True)
class FactResolution:
    status: str
    answer: str | None
    message: str


def _parse_utc(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _unavailable():
    # All denials, missing facts, and bad sources have the same guest-visible
    # result so callers cannot probe another room or property's records.
    return FactResolution("unavailable", None, FACT_UNAVAILABLE_MESSAGE)


def _authorize_scope(*, context, business_id, record_business_id, hotel_id,
                     trusted_snapshot_hotel_id, snapshot, stay_id, room_id):
    if not isinstance(context, AccessContext):
        raise AccessDenied("authorization_context_missing")
    if business_id != record_business_id or hotel_id != context.hotel_id:
        raise AccessDenied("wrong_business")
    indexes = validate_snapshot(snapshot)
    if context.role == "guest":
        if not stay_id or not room_id:
            raise AccessDenied("guest_scope_denied")
        authorize_hotel_snapshot(
            context, business_id=business_id,
            record_business_id=record_business_id,
            resource="guest_stay_summary", action="read", snapshot=snapshot,
            trusted_snapshot_hotel_id=trusted_snapshot_hotel_id,
            record_guest_id=context.guest_id, stay_id=stay_id, room_id=room_id,
        )
    else:
        authorize_access(
            context, business_id=business_id,
            record_business_id=record_business_id,
            resource="room_inventory", action="read", record_hotel_id=hotel_id,
        )
        if (trusted_snapshot_hotel_id != context.hotel_id
                or not isinstance(trusted_snapshot_hotel_id, str)):
            raise AccessDenied("hotel_mapping_unverified")
    if room_id is not None and room_id not in indexes["rooms"]:
        raise AccessDenied("invalid_record_reference")
    return indexes


@dataclass(frozen=True)
class _FactPreflight:
    topic: FactTopic
    policy: FactSourcePolicy
    room_index: dict
    business_id: str
    hotel_id: str
    room_id: str | None
    current: datetime
    max_age: timedelta


def _preflight(*, topic, context, business_id, record_business_id, hotel_id,
               trusted_snapshot_hotel_id, snapshot, stay_id, room_id,
               approved_sources, max_age, now):
    """Establish trusted scope and source policy before any provider read."""
    try:
        normalized_topic = FactTopic(topic)
        if not isinstance(max_age, timedelta) or max_age <= timedelta(0):
            return _unavailable()
        policy = (approved_sources or {}).get(normalized_topic)
        if (not isinstance(policy, FactSourcePolicy)
                or not isinstance(policy.scope, FactScope)
                or any(not isinstance(part, str) or not part.strip()
                       for part in (policy.namespace, policy.table, policy.field_id))):
            return _unavailable()
        indexes = _authorize_scope(
            context=context, business_id=business_id,
            record_business_id=record_business_id, hotel_id=hotel_id,
            trusted_snapshot_hotel_id=trusted_snapshot_hotel_id,
            snapshot=snapshot, stay_id=stay_id, room_id=room_id,
        )
        current = _parse_utc(now)
        if current is None:
            return _unavailable()
        return _FactPreflight(normalized_topic, policy, indexes["rooms"],
                              business_id, hotel_id, room_id, current, max_age)
    except (AccessDenied, KeyError, TypeError, ValueError, AttributeError):
        return _unavailable()


def _resolve_preflight(records, observed_at, preflight):
    """Resolve only after preflight; never copy source metadata to the result."""
    if not isinstance(records, (list, tuple)):
        return _unavailable()
    snapshot_time = _parse_utc(observed_at)
    if (snapshot_time is None or preflight.current < snapshot_time
            or preflight.current - snapshot_time > preflight.max_age):
        return _unavailable()

    matching = []
    for record in records:
        if not isinstance(record, HotelFactRecord):
            return _unavailable()
        if record.topic != preflight.topic:
            continue
        if (record.business_id != preflight.business_id
                or record.hotel_id != preflight.hotel_id):
            return _unavailable()
        if (record.source_namespace != preflight.policy.namespace
                or record.source_table != preflight.policy.table
                or record.source_field != preflight.policy.field_id
                or record.scope != preflight.policy.scope):
            return _unavailable()
        value = record.value
        if (not isinstance(value, str) or not value.strip()
                or len(value) > MAX_FACT_TEXT):
            return _unavailable()
        fact_time = _parse_utc(record.observed_at)
        if (fact_time is None or fact_time > preflight.current
                or preflight.current - fact_time > preflight.max_age):
            return _unavailable()
        if preflight.policy.scope == FactScope.ROOM:
            if (not preflight.room_id or record.room_id != preflight.room_id
                    or record.room_id not in preflight.room_index):
                return _unavailable()
        elif record.room_id is not None:
            return _unavailable()
        matching.append(record)

    if len(matching) != 1:
        return _unavailable()
    answer = matching[0].value.strip()
    return FactResolution("answered", answer, answer)


def resolve_hotel_fact(topic, records, *, context, business_id,
                       record_business_id, hotel_id,
                       trusted_snapshot_hotel_id, snapshot,
                       observed_at, now, stay_id=None, room_id=None,
                       approved_sources=None, max_age=MAX_FACT_AGE):
    """Resolve one allowlisted, fresh fact under trusted business/stay scope.

    ``approved_sources`` is server-controlled contract configuration with
    ``FactTopic`` keys and ``FactSourcePolicy`` values. Empty or missing
    configuration always returns unavailable. The function intentionally
    accepts no free-form question, model-generated filter, or caller-selected
    source. Guest facts require the existing active registered-stay checks.
    """
    preflight = _preflight(
        topic=topic, context=context, business_id=business_id,
        record_business_id=record_business_id, hotel_id=hotel_id,
        trusted_snapshot_hotel_id=trusted_snapshot_hotel_id,
        snapshot=snapshot, stay_id=stay_id, room_id=room_id,
        approved_sources=approved_sources, max_age=max_age, now=now,
    )
    if isinstance(preflight, FactResolution):
        return preflight
    return _resolve_preflight(records, observed_at, preflight)


def resolve_hotel_fact_from_reader(reader, topic, **scope):
    """Use an injected read-only adapter and sanitize provider failures.

    The reader contract is ``reader(topic=..., business_id=..., hotel_id=...,
    room_id=...) -> (records, observed_at)``. Its implementation must use
    authenticated Workpeg reads, complete pagination and the canonical hotel
    snapshot validator. No writes, arbitrary query text, row IDs, or model
    filters are passed to it. This adapter is not wired to a live Workpeg
    reader until an approved facts source and guest scope exist.
    """
    if not callable(reader):
        return _unavailable()
    preflight = _preflight(
        topic=topic, context=scope.get("context"),
        business_id=scope.get("business_id"),
        record_business_id=scope.get("record_business_id"),
        hotel_id=scope.get("hotel_id"),
        trusted_snapshot_hotel_id=scope.get("trusted_snapshot_hotel_id"),
        snapshot=scope.get("snapshot"), stay_id=scope.get("stay_id"),
        room_id=scope.get("room_id"),
        approved_sources=scope.get("approved_sources"),
        max_age=scope.get("max_age", MAX_FACT_AGE), now=scope.get("now"),
    )
    if isinstance(preflight, FactResolution):
        return preflight
    try:
        records, observed_at = reader(
            topic=preflight.topic,
            business_id=scope.get("business_id"),
            hotel_id=scope.get("hotel_id"),
            room_id=scope.get("room_id"),
        )
    except Exception:
        # Provider errors may contain URLs, row data, or credentials. Never
        # include them in a guest-facing result or ordinary logs.
        return _unavailable()
    # Revalidate authorization after I/O as well. The reader's returned
    # timestamp, never a caller-provided timestamp, controls fact freshness.
    scope.pop("observed_at", None)
    return resolve_hotel_fact(preflight.topic, records,
                              observed_at=observed_at, **scope)
