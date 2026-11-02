# Sales dashboard (React)

Standalone React + TypeScript + Vite dashboard for the `print_db` sales data,
styled with Tailwind CSS v4 and shadcn/ui tokens. The Streamlit app in the
repository root is unchanged.

## Requirements

- Node.js 20+
- Python virtual environment at `../venv` with `requirements.txt` installed
- `.env` in the repository root with `DB_HOST`, `DB_PORT`, `DB_USER`,
  `DB_PASSWORD`, and `DB_NAME`

## Data

The UI reads a generated TypeScript snapshot from `src/data/dashboard-data.ts`.
It does not query MySQL at runtime. Regenerate it after the database changes:

```powershell
..\venv\Scripts\python.exe ..\scripts\build_dashboard_data.py
```

Or, with the virtual environment activated:

```bash
npm run data
```

The generator joins `sales_details` to `product_group`, `product`, and `brand`
and writes the snapshot. It computes:

- last 30 days vs the prior 30 days for revenue and units
- hourly unit counts for the last 3 weeks, split by `STO001` and `STO002`
- the top 6 product groups by last-30-day revenue
- the last 12 months for the seasonality radar
- `n/a` for the yearly delta when the prior 12-month window is incomplete

## Run

```bash
npm install
npm run dev
```

Production build and local preview:

```bash
npm run build
npm run preview
```

## shadcn/ui + Tailwind + TypeScript setup

This project already follows the shadcn layout:

- `components.json` maps `@/components`, `@/components/ui`, `@/lib/utils`, and
  `@/hooks`
- `tsconfig.app.json` defines the `@/*` path alias (without `baseUrl`)
- `vite.config.ts` resolves `@` to `src`
- `src/index.css` contains Tailwind v4 and the shadcn CSS variables/tokens
- `src/lib/utils.ts` exports `cn`
- `src/components/ui/analytics-bento.tsx` is the copied component

The `/components/ui` folder matters because the shadcn CLI writes generated
primitives there and `components.json` aliases that path. Keeping the component
there lets `npx shadcn@latest add ...` coexist without rewriting imports.

To bootstrap the same setup in another Vite app:

```bash
npm create vite@latest my-app -- --template react-ts
cd my-app
npm install tailwindcss @tailwindcss/vite lucide-react
npx shadcn@latest init
npx shadcn@latest add button
```

Then add the `@tailwindcss/vite` plugin and the `@` alias to `vite.config.ts`,
and import `./index.css` from `src/main.tsx`.

## Structure

```text
src/
  App.tsx                          page shell, header, theme toggle, footer
  components/ui/analytics-bento.tsx
  data/dashboard-data.ts           generated database snapshot
  index.css                        Tailwind v4 + shadcn tokens
  lib/utils.ts                     cn helper
../scripts/build_dashboard_data.py root-level data generator
```
