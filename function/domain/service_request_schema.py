"""Proposed Workpeg tables for WOR-14; this module never provisions them."""
from copy import deepcopy

from .schema import choice, field, instant, ref
from .service_requests import DEPARTMENTS, ORIGINS, STATUSES, URGENCIES


REQUEST_COLUMNS = [
    ref("request_id"), field("idempotency_key"), ref("hotel_id"), ref("stay_id"),
    ref("room_id"), ref("guest_id"), choice("origin", *ORIGINS),
    choice("category", "unknown", "extra_towels", "linen", "room_cleaning",
           "toiletries", "plumbing", "electrical", "air_conditioning",
           "room_equipment", "room_service", "dining", "minibar", "transport",
           "wake_up_call", "billing_question", "general_help"),
    field("category_detail"), choice("department", *DEPARTMENTS),
    field("description"), choice("urgency", *URGENCIES),
    choice("status", *STATUSES), field("assigned_staff_id", required=False),
    field("triage_required", "boolean"), field("sensitive", "boolean"),
    instant("created_at"), instant("updated_at"), instant("received_at"),
    instant("acknowledge_by"), instant("due_at"), instant("assigned_at", False),
    instant("acknowledged_at", False), instant("in_progress_at", False),
    instant("resolved_at", False), instant("reopened_at", False),
    instant("cancelled_at", False), instant("escalated_at", False),
    field("version", "number"), ref("last_event_id"),
    field("last_operation_signature"),
]

EVENT_COLUMNS = [
    ref("event_id"), ref("operation_id"), field("operation_signature"),
    ref("request_id"), ref("hotel_id"),
    field("sequence", "number"), choice("event_type", "created", "status_changed", "triaged"),
    field("from_status", required=False), choice("to_status", *STATUSES),
    field("actor_id"), choice("actor_kind", "guest", "staff"),
    field("actor_department", "mutable_select", required=False,
          choices=DEPARTMENTS), instant("occurred_at"),
    field("reason", required=False), choice("commit_state", "pending", "committed"),
]


def _table(name, alias, columns):
    return {
        "name": name,
        "alias": alias,
        "namespace": "roomay_requests_v1",
        "permission": "700",
        "metadata": {"extra": {"contract": "roomay.service_requests.v1"}},
        "columns": [dict(deepcopy(column), position=(index + 1) * 1000)
                    for index, column in enumerate(columns)],
    }


def proposed_service_request_tables():
    """Owner-only schemas; live creation is gated by WOR-28/WOR-29."""
    return [
        _table("Roomay Service Requests", "roomay-service-requests-v1", REQUEST_COLUMNS),
        _table("Roomay Service Request Audit", "roomay-service-request-audit-v1", EVENT_COLUMNS),
    ]
