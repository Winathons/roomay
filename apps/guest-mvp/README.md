# Roomay Guest MVP preview

This is a standalone React/Vite preview of the WOR-17 guest stay-code, conversation, request review, and tracking flow. It preserves the approved Roomay guest UI treatment while keeping the guest preview independent from `apps/web` and its prototype store.

![Roomay Guest MVP stay-code screen](docs/guest-mvp-preview.png)

## Run locally

From this directory:

```sh
npm ci
npm run dev
```

Open `http://127.0.0.1:5173/` or `http://127.0.0.1:5173/#/guest/mvp`. Both URLs render the same flow. The preview code is `482913`; `000000` exercises the expired-code error, other six-digit codes exercise incorrect-code handling (three attempts), and `?stay=ended` exercises the ended-stay error. To inspect simulated save outcomes, open with `?preview=fail`, `?preview=unknown`, or `?preview=offline` and proceed to request confirmation.

| Command | Purpose |
|---|---|
| `npm run typecheck` | TypeScript checks |
| `npm run lint` | ESLint |
| `npm run build` | Regenerate used icon exports, typecheck, and build to `dist/` |
| `npm run preview` | Serve the production build |

## Preview boundaries

All stay codes, room details, deterministic replies, triage, saves, and tracking shown here are simulation fixtures held in the browser session. They do not verify a real guest, read WorkPeg tables, call WorkPeg AI, notify staff, or create operational hotel records. No WorkPeg integration or credentials are included. Keep this preview out of a hotel release until verified stay access and trusted chat/action integrations are implemented and end-to-end verified.

## Layout

- `src/main.tsx`, `src/App.tsx`: standalone entry and root/hash-route rendering.
- `src/GuestMvp.tsx`: guest stay-code, conversation, review, confirmation, tracking, and error states.
- `src/PhoneShell.tsx`: phone frame extracted from the visual reference.
- `src/triage.ts`: deterministic preview-only request classification.
- `src/styles.css`: Roomay visual tokens and the original guest screen styles.
- `scripts/gen-icons.mjs`, `src/icons.js`: app-local generated Tabler exports used by Vite.

The standalone package has its own `package.json` and lockfile. It has no runtime imports from `apps/web`.
