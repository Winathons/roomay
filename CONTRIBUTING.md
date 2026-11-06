
# Contributing to Roomay

Roomay is a Workpeg-native hotel operations
and AI guest experience application.

## Getting started

1. Clone the repository.
2. Create and activate a Python virtual environment.
3. Run `pip install -r requirements-dev.txt`.
4. Run `workpeg ui serve ui/`.
5. Run `workpeg ui build ui/` to verify compilation.

## Claiming tasks

All tasks are created unassigned in Linear.

1. Choose an available issue.
2. Assign yourself.
3. Move the issue to In Progress.
4. Read its acceptance criteria before coding.

## Branches and pull requests

Never work directly on main.

Create branches using Linear issue IDs:

`WOR-8-hotel-data-model`

Open a pull request with the issue ID in
the title or description.

Each PR should include:
- What changed
- How it was tested
- Screenshots for visible UI changes
- Known limitations or blockers

Request review before merging.

## Definition of Done

An issue is Done only when:
- Acceptance criteria are satisfied
- Changes have been tested
- The PR has been merged
- Relevant documentation is updated

## Security

- Never commit API keys or developer tokens.
- Use fictional guests and hotel records.
- Workpeg development may contact real platform APIs.
- Do not use a production hotel's business account.
- Never expose privileged Workpeg credentials
  in frontend code.

## Project tracking

Linear:
https://linear.app/workpeg

Repository:
https://github.com/Umardoja/roomay
