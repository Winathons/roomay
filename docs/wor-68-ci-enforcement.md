# WOR-68 — enforce main PR checks (owner action)

Last inspected: **12 November 2026**. This runbook is an operational checklist, not evidence that branch protection was changed.

## Verified current facts

- Default branch: `main`. The old remote `staging` branch returned 404 on the GitHub Branch API and is no longer part of the workflow.
- Active ruleset: [protect main, #27075713](https://github.com/Winathons/roomay/rules/27075713), targeting `refs/heads/main`.
- The ruleset currently requires PRs, review-thread resolution and no force-push/deletion; its **`required_status_checks.parameters.required_status_checks` is empty** at the time of inspection. **Therefore passing CI is not yet a GitHub-enforced merge condition.**
- The actual GitHub Actions workflow is `Roomay UI Check`; the job/check name to require is exactly **`Workpeg UI build`**. Verified on recent successful PR runs, including [#167](https://github.com/Winathons/roomay/actions/runs/43251828869).
- `.github/workflows/workpeg-ui.yml` now triggers `pull_request` and `push` events to **`main` only** and preserves all offline unit, Docker voice/intent smoke, Workpeg UI compiler and WOR-33 release-bundle checks. `tests/test_main_branch_workflow.py` pins this configuration.

## GitHub ruleset change — owner action

With a repo-admin GitHub session:

1. Open [protect main](https://github.com/Winathons/roomay/rules/27075713) and edit the existing active ruleset; **do not** create a conflicting second protection rule.
2. Under **Require status checks to pass before merging**, configure exactly **`Workpeg UI build`** from GitHub Actions. Preserve **Require a pull request**, review-thread resolution, and the rules preventing deletion and force pushes.
3. Preserve the current strict/up-to-date requirement unless intentionally revising it. Prefer the actual GitHub Actions app as the expected source if GitHub prompts for one; do **not** register an imaginary check.
4. Save; reload the ruleset and confirm `required_status_checks` contains `context: Workpeg UI build`. Do not copy secrets or admin tokens into PRs or Linear.
5. On a future **new** PR to main, observe the check pending, then passing; on an intentionally failing **test-only branch** (if needed and owner-approved), verify merge is prevented. Do not alter or publish real Workpeg data for this test.
6. Confirm no bypass actor can silently skip the restriction. Note branch settings can evolve; recheck with the [GitHub ruleset API](https://api.github.com/repos/Winathons/roomay/rulesets/27075713) or UI before marking WOR-68 complete.

## Out of scope and remaining gates

- This code PR **cannot configure the GitHub ruleset**; it only removes legacy CI branch filters, pins the check identity and explains the owner action. GitHub settings remain unchanged until an administrator edits and verifies them.
- Merging main does **not** auto-deploy, publish or install a Workpeg Peg. Workpeg publishing, production secret handling, rollback and identity/security acceptance remain a separate owner-controlled release gate under WOR-25/61/62.
- Do not introduce force pushes, delete protected branches, reactivate `staging`, widen Workpeg table permissions, run `--fake-cloud` in CI, or claim local mock requests are real hotel operations.
- The main-only workflow migration and old PR retargeting are already done, but **WOR-68 stays In Progress until the GitHub required check is actually enforced** and the deployment strategy is separately documented/verified.
