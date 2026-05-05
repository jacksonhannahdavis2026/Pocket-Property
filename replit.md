# Workspace

## Overview

pnpm workspace monorepo using TypeScript. Each package manages its own dependencies.

## Stack

- **Monorepo tool**: pnpm workspaces
- **Node.js version**: 24
- **Package manager**: pnpm
- **TypeScript version**: 5.9
- **API framework**: Express 5
- **Database**: PostgreSQL + Drizzle ORM
- **Validation**: Zod (`zod/v4`), `drizzle-zod`
- **API codegen**: Orval (from OpenAPI spec)
- **Build**: esbuild (CJS bundle)

## Streamlit App — Real Estate Investment Evaluator

Located in `streamlit-app/`. Runs on port 5000 via the "Start application" workflow.

- `streamlit-app/app.py` — main UI and input form
- `streamlit-app/underwriting.py` — financial calculations (mortgage, NOI, cap rate, CoC, DSCR, ROI)
- `streamlit-app/scenarios.py` — bear/base/bull scenario builder
- `streamlit-app/verdicts.py` — buy/maybe/pass scoring logic
- `streamlit-app/.streamlit/config.toml` — headless server config
- `streamlit-app/requirements.txt` — streamlit + pandas

## Key Commands

- `pnpm run typecheck` — full typecheck across all packages
- `pnpm run build` — typecheck + build all packages
- `pnpm --filter @workspace/api-spec run codegen` — regenerate API hooks and Zod schemas from OpenAPI spec
- `pnpm --filter @workspace/db run push` — push DB schema changes (dev only)
- `pnpm --filter @workspace/api-server run dev` — run API server locally

See the `pnpm-workspace` skill for workspace structure, TypeScript setup, and package details.
