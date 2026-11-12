"""ROOMAY's inactive Workpeg Function entrypoint.

The real Workpeg platform invokes `main(context, payload)` for table hooks or
approved manifest actions. No hook or action is installed for ROOMAY yet.
This intentionally refuses every invocation until an authorized, reviewed
business operation and its persistence/audit guarantees are implemented.

Never forward a platform-supplied context token to a standalone service, log
the context, or treat a synthetic test envelope as verified staff identity.
"""


def main(context: dict, payload: dict) -> dict:
    """Deny all unconfigured actions; never return a successful write result."""
    if not isinstance(context, dict) or not isinstance(payload, dict):
        raise ValueError("invalid_workpeg_function_envelope")
    raise RuntimeError("roomay_function_not_configured")
