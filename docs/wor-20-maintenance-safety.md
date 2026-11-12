# WOR-20 — maintenance safety contract

**Status: offline-only. No hosted Workpeg writes or deployment.**

The canonical `room_blocks` table contains `entity_id`, `room_id`, `start`, `end`, `reason`, `status` (`active`/`released`). Permissions remain owner-only `700`. Do not migrate this table without a reviewed owner-authorized plan.

## Commands

`domain/maintenance_commands.py` prepares, but never persists, three sensitive actions:

- **Create block:** requires trusted same-business/hotel context, maintenance supervisor/owner/manager authority, fresh complete safety snapshot, real serialization guard, valid interval, reason, repair criteria and idempotency. Returns proposed block/audit, identifies active stays for human follow-up. No guest is moved.
- **Release block:** requires the same authority, independently verified repair and evidence reference. Returns proposed release/audit. A formerly ready room becomes `inspection`, not ready; housekeeping must clear it separately.
- **Suggest/reassign:** only authorized reception/management for a confirmed booking without an existing stay. Suggest only ready, enabled, unoccupied, nonoverlapping, unblocked same-type alternatives. Reassignment returns a human-reviewed proposal/audit; no booking is changed automatically. Checked-in guest moves belong to WOR-12.

An active maintenance block remains unsafe **even after its planned end date** until explicitly released. A booking ending before block start is unaffected.

`maintenance_supervisor` is a proposed role requiring verified provider identity and department mapping; a browser or AI claim is never sufficient. `OperationContext` itself is not authentication. Deterministic operation IDs are not a database unique constraint or a durable audit.

## Required before real operation

The canonical block table cannot persist repair criteria, verified evidence, supervisor signoff or an audit-operation identity; these appear in the plan only. A future approved schema/authoritative audit design must store them durably. The future adapter must verify actor/business/department, serialize competing operations, enforce durable idempotency and committed audit history, reconcile partial or uncertain writes through fresh readback and visibly propagate staff state. Until Workpeg's supported writer/authorization path is established, these plans must not be exposed as committed actions.

The module always reports `persisted=False`; no permission grants, hosted data mutations or Workpeg Function calls occur.

## Tests

```bash
python -m unittest tests.test_maintenance_commands tests.test_hotel -v
python -m unittest discover -s tests -v
python -m compileall -q ui function domain tests
workpeg ui build ui/
python -m unittest tests.test_release_candidate -v
```

These synthetic tests do not prove Workpeg persistence, staff authorization, concurrent room locking or real hotel readiness. Keep WOR-20 In Progress until hosted block+audit readback, separate-session permissions, human release, housekeeping and booking/check-in safety are demonstrated.
