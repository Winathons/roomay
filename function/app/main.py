"""Read-only metadata acceptance entrypoint for one approved manifest action.

No action is registered in the production manifest and no hook is attached.
This handler uses only Workpeg's invocation context, performs metadata GETs
for the two canonical namespaces, and returns sanitized status flags. It does
not read rows or invoke any write method.
"""

from domain.workpeg_adapter import AdapterError, resolve_tables_for_write
from domain.workpeg_function_tables import FunctionTablesError, WorkpegFunctionTables


_UNVERIFIED = {
    "authorization": "unverified",
    "inventory": "incomplete",
    "peg_scope": "unverified",
    "business_scope": "unverified",
    "actor_presence": "unverified",
}


def _denied(**updates):
    result = dict(_UNVERIFIED)
    result["authorization"] = "denied"
    result.update(updates)
    return result


def _failure(error, *, lists_authorized):
    code = getattr(error, "code", "")
    if code == "function_peg_scope_mismatch":
        return _denied(peg_scope="mismatch")
    if code == "function_business_scope_mismatch":
        return _denied(business_scope="mismatch")
    if lists_authorized:
        return {
            "authorization": "authorized",
            "inventory": "incomplete",
            "peg_scope": "match",
            "business_scope": "match",
            "actor_presence": "verified",
        }
    if getattr(error, "status", None) in (401, 403):
        return _denied()
    return dict(_UNVERIFIED)


def main(context: dict, payload: dict) -> dict:
    """Validate one invocation-scoped read-only inventory request.

    Workpeg supplies ``business``, ``token``, ``staff`` and ``phase``. The
    action payload must be empty; it cannot override the actor, Peg, token, or
    business. A successful business match means the authenticated Tables GETs
    were made for this platform-supplied business, not that this handler has a
    hard-coded Roomay AI business allowlist. The owner must verify the selected
    Workpeg business before invoking the test action.
    """
    if not isinstance(context, dict) or not isinstance(payload, dict) or payload:
        raise ValueError("invalid_workpeg_function_envelope")
    if context.get("phase") != "post_save_hook":
        raise RuntimeError("roomay_readonly_action_context_invalid")

    staff = context.get("staff")
    if not isinstance(staff, dict) or not isinstance(staff.get("email"), str) or not staff["email"].strip():
        return _denied()

    lists_authorized = False
    try:
        business_id = context.get("business")
        tables = WorkpegFunctionTables(
            context, expected_business_id=business_id)
        inventory = {
            "roomay_hotel_v1": tables.get_tables("roomay_hotel_v1"),
            "roomay_requests_v1": tables.get_tables("roomay_requests_v1"),
        }
        lists_authorized = True
        actor_id = tables.staff_email
        attestation = tables.attest_inventory(
            inventory, business_id=tables.business_id, actor_id=actor_id)
        resolve_tables_for_write(
            inventory,
            scope_attestation=attestation,
            business_id=tables.business_id,
            actor_id=actor_id,
            peg_namespace=tables.peg_namespace,
        )
    except (FunctionTablesError, AdapterError) as error:
        return _failure(error, lists_authorized=lists_authorized)
    except Exception:
        # Never reflect a token, actor identity, response or arbitrary error.
        if lists_authorized:
            return {
                "authorization": "authorized",
                "inventory": "incomplete",
                "peg_scope": "match",
                "business_scope": "match",
                "actor_presence": "verified",
            }
        return _denied()

    return {
        "authorization": "authorized",
        "inventory": "complete",
        "peg_scope": "match",
        "business_scope": "match",
        "actor_presence": "verified",
    }
