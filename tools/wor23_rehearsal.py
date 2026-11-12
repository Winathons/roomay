"""WOR-23: one-command, *synthetic-only* cross-workspace demo rehearsal.

This script intentionally creates no network server, performs no Workpeg or
PostgreSQL writes, and does not produce hosted acceptance evidence.
Run: python -m tools.wor23_rehearsal
"""
import json
from copy import deepcopy
from dataclasses import replace

from domain.checkout_commands import OperationContext
from domain.fixtures import synthetic_hotel, uid
from domain.maintenance_commands import (
    eligible_reassignment_rooms, prepare_safe_reassignment,
)
from tools.guest_chat_demo import DemoError, GuestChatDemo


def _require(condition, label):
    if not condition:
        raise AssertionError("synthetic_rehearsal_failed:" + label)


def _role_denied(action, expected_code):
    try:
        action()
    except DemoError as error:
        _require(error.status == 403 and error.code == expected_code,
                 "role_denial_reason")
        return
    raise AssertionError("synthetic_rehearsal_failed:role_denial_missing")


def run_synthetic_rehearsal():
    """Return sanitized, reproducible evidence; no real staff or guest action."""
    steps = []
    demo = GuestChatDemo(max_sessions=6)
    guest_session, view = demo.create_session()
    _require(view["workspace"] == "guest", "initial_guest_workspace")
    _require(view["requests"] == [], "initial_requests_empty")
    steps.append("guest_example_stay_loaded")

    pending = demo.send_message(
        guest_session, "Please bring extra towels to room 205."
    )
    _require(pending["state"] == "awaiting_confirmation",
             "explicit_guest_confirmation_required")
    revision = pending["pending"]["revision"]
    _require(not pending["submitted"] and not pending["persisted"],
             "guest_request_not_live")
    steps.append("guest_towel_intent_reviewed")

    result = demo.confirm(guest_session, revision)
    _require("has not been sent to hotel staff" in result["messages"][-1]["text"],
             "synthetic_confirmation_disclaimer")
    guest = demo.role_view(guest_session)
    _require(len(guest["requests"]) == 1
             and guest["requests"][0]["status"] == "received",
             "guest_receives_synthetic_ticket")
    demo.confirm(guest_session, revision)
    _require(len(demo.role_view(guest_session)["requests"]) == 1,
             "duplicate_confirmation_not_appended")
    steps.append("guest_confirmed_once_in_process")

    _role_denied(
        lambda: demo.assign_latest_to_housekeeping(guest_session),
        "demo_reception_role_required",
    )
    steps.append("guest_cannot_run_staff_actions")

    reception = demo.switch_role(guest_session, "reception")
    _require(reception["workspace"] == "reception"
             and len(reception["requests"]) == 1,
             "reception_sees_synthetic_ticket")
    request_id = reception["requests"][0]["request_id"]
    reception = demo.assign_latest_to_housekeeping(guest_session, request_id)
    _require(reception["requests"][0]["status"] == "assigned",
             "reception_assigns_ticket")
    steps.append("reception_assigned_housekeeping")

    housekeeping = demo.switch_role(guest_session, "housekeeping")
    _require(housekeeping["workspace"] == "housekeeping"
             and len(housekeeping["requests"]) == 1
             and "guest" not in housekeeping,
             "housekeeping_scope")
    for action, expected in (
        ("acknowledge", "acknowledged"),
        ("start", "in_progress"),
        ("resolve", "resolved"),
    ):
        housekeeping = demo.department_action(guest_session, action, request_id)
        _require(housekeeping["requests"][0]["status"] == expected,
                 "housekeeping_" + action)
        steps.append("housekeeping_" + expected)
    _require(housekeeping["requests"][0]["activity"] == [
        "received", "assigned", "acknowledged", "in_progress", "resolved",
    ], "canonical_audit_lifecycle")

    _role_denied(
        lambda: demo.send_message(guest_session, "Please send towels"),
        "demo_guest_role_required",
    )
    demo.switch_role(guest_session, "guest")
    guest = demo.resume_session(guest_session)
    _require(guest["requests"][0]["status"] == "resolved",
             "guest_readback_after_qa_switch")
    serialized = json.dumps(guest)
    _require("request_id" not in serialized and "guest_id" not in serialized
             and "operation_signature" not in serialized
             and "metrics" not in guest,
             "guest_projection_privacy")
    steps.append("guest_reads_resolved_on_same_process_reload")

    other_session, other = demo.create_session()
    _require(other_session != guest_session
             and other["requests"] == []
             and len(other["chat"]["messages"]) == 1,
             "separate_session_privacy")
    mismatch = demo.send_message(other_session,
                                 "Please bring towels to room 204.")
    _require(mismatch["state"] == "handoff"
             and mismatch["pending"] is None,
             "unverified_room_denied")
    _require(demo.role_view(other_session)["requests"] == [],
             "wrong_room_no_ticket")
    steps.append("wrong_room_and_other_session_denied")

    failed_session, _ = demo.create_session()
    failed = demo.send_message(
        failed_session, "AC trouble in room 205", _provider_status="failed"
    )
    _require(failed["state"] == "unavailable"
             and not failed["submitted"]
             and not failed["persisted"]
             and not demo.role_view(failed_session)["requests"],
             "provider_failure_no_write")
    steps.append("provider_failure_no_guest_submission")

    # Separate synthetic inventory check: not the same in-memory browser
    # transaction, and NOT proof of a serialized hosted Workpeg operation.
    hotel = synthetic_hotel()
    original = deepcopy(hotel)
    hotel["room_blocks"].append({
        "entity_id": uid("wor23-synthetic-maintenance-block"),
        "room_id": uid("201"), "start": "2026-11-13",
        "end": "2026-11-14", "reason": "Synthetic cooling maintenance",
        "status": "active",
    })
    context = OperationContext(
        business_id=uid("wor23-business"),
        snapshot_business_id=uid("wor23-business"),
        hotel_id=uid("wor23-hotel"),
        snapshot_hotel_id=uid("wor23-hotel"),
        actor_id="synthetic-manager",
        actor_role="manager", authorization_verified=True,
        snapshot_fresh=True, serialization_guard_held=True,
        authoritative_now="2026-11-12T10:00:00+01:00",
        safety_snapshot_complete=True,
    )
    alternatives = eligible_reassignment_rooms(
        hotel, reservation_id=uid("future"), context=context
    )
    _require(any(row["room_id"] == uid("204") for row in alternatives),
             "eligible_alternative_exists")
    move = prepare_safe_reassignment(
        hotel, reservation_id=uid("future"),
        alternative_room_id=uid("204"),
        idempotency_key="wor23-safety-alternative-01", context=context
    )
    _require(move.reservation_before["room_id"] == uid("201")
             and move.reservation_after["room_id"] == uid("204")
             and move.persisted is False
             and hotel["reservations"][0]["room_id"] == uid("201"),
             "maintenance_refuses_unsafe_booking_without_write")
    _require(hotel["stays"] == original["stays"],
             "no_automatic_guest_movement")
    steps.append("separate_offline_blocked_room_reassignment_plan")

    return {
        "issue": "WOR-23",
        "outcome": "synthetic_rehearsal_passed",
        "evidence_scope": "local_process_only",
        "steps": steps,
        "verified": {
            "synthetic_towel_request_lifecycle": True,
            "synthetic_guest_readback_same_process": True,
            "synthetic_role_isolation": True,
            "synthetic_duplicate_confirmation": True,
            "synthetic_provider_failure": True,
            "separate_synthetic_room_safety_plan": True,
        },
        "not_verified": [
            "real_workpeg_guest_request_write",
            "real_workpeg_department_staff_auth_and_readback",
            "cross_process_or_cross_server_persistence",
            "oidc_callback_with_registered_client",
            "authoritative_maintenance_or_reassignment_write",
            "actual_voice_call_or_ai_provider",
            "real_payment_or_pms_integration",
        ],
        "record_writes": "none_external; process_memory_only",
    }


def main():
    print(json.dumps(run_synthetic_rehearsal(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
