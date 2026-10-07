# Frontend — Explain My Error Like I'm Losing My Mind

Next.js (App Router) + TypeScript + Tailwind CSS v4 + Monaco Editor.
See the [project README](../README.md) for the full setup.

```bash
npm install          # also copies Monaco assets into public/ (offline-friendly)
npm run dev          # http://localhost:3000
npm run typecheck    # tsc --noEmit
npm run lint
npm run build
```

Set `NEXT_PUBLIC_API_URL` in `.env.local` if the backend is not on `http://localhost:8000`
(see `.env.local.example`).

## Layout

```
app/page.tsx          the dashboard: state, SSE handling, layout
components/
  CodeEditor.tsx      Monaco, with red highlighting of the root-cause lines
  ErrorInput.tsx      error textarea + optional expected output
  ActionBar.tsx       explanation-mode dropdown + the two buttons
  AttemptTracker.tsx  "Debugging journey" — the live agent loop
  FixPanel.tsx        proposed fix, diff, verification badge
  WhyItWorked.tsx     the "Why Did My Fix Work?" section
  ExplanationPanel.tsx / DiffViewer.tsx / ExecutionResult.tsx / DebugHistory.tsx
  Panel.tsx, CodeBlock.tsx, Markdown.tsx, ui/   shared primitives
lib/api.ts            typed API client incl. the SSE parser
types/debug.ts        mirrors backend/app/models/schemas.py
```

`npm run postinstall` copies Monaco from `node_modules` into `public/monaco`, so the editor
loads without a CDN. That folder is git-ignored and regenerated on install.
