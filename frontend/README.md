# AI Operational Twin — Frontend

React + Vite dashboard for Ekak Innovations. Displays waste-cost KPIs, time-series and per-machine charts, a top waste-events table, and an AI chat assistant — all values in INR. Built to run fully on mock data so the UI is developed independently of the backend, then switched to live data with a single environment flag.

---

## Setup

### Prerequisites

- Node.js 18+ and npm
- The backend running locally if you want live data (see "Connecting to the backend"). The UI runs without it using mocks.

### Install

```bash
cd frontend
npm install
```

### Run

```bash
npm run dev
```

Opens the dashboard at `http://localhost:5173` (or the next free port, e.g. `5174`, if 5173 is taken — the terminal prints the actual URL).

### Configure

Copy the template:

```bash
cp .env.example .env
```
And configure as necessary.

> **Note:** `.env` is read only when the dev server starts. After editing it, stop the server (`Ctrl+C`) and run `npm run dev` again. Normal code files hot-reload automatically; `.env` does not.

---

## Project Structure

```
frontend/
├── index.html                  # Page shell, sets the tab title and mount node
├── package.json                # Dependencies (react, recharts, vite)
├── vite.config.js              # React plugin + /api proxy to the backend gateway
├── .env.example                # Environment variable template
│
└── src/
    ├── main.jsx                # React entry — mounts <App/>
    ├── App.jsx                 # Layout shell; owns the shared `view` state
    ├── index.css               # Design tokens (brand colours) + layout grid + all styles
    │
    ├── config/
    │   └── constants.js        # API base, refresh interval, view roles, brand colours
    │
    ├── api/
    │   └── client.js           # The only file that fetches. One function per endpoint + mock switch
    │
    ├── mocks/
    │   └── mockData.js         # Fixtures shaped exactly like the real API, for VITE_USE_MOCKS=true
    │
    ├── utils/
    │   └── format.js           # formatINR (en-IN ₹), formatPercent, formatTime, formatDelta
    │
    ├── hooks/
    │   ├── useApiResource.js   # Generic fetch + polling + loading/error engine
    │   ├── useKpis.js          # KPI data for a view
    │   ├── useWasteOverTime.js # Time-series data
    │   ├── useWasteByMachine.js# Per-machine ranking data
    │   ├── useTopEvents.js     # Top-5 waste events
    │   └── useChat.js          # Chat conversation state + send()
    │
    └── components/
        ├── TopBar.jsx          # Title, last-updated time, view toggle
        ├── ViewToggle.jsx      # CEO / Factory Manager / Department Manager buttons
        ├── KpiGrid.jsx         # Fetches KPIs, renders 4 cards
        ├── KpiCard.jsx         # One metric card (label, value, delta, accent colour)
        ├── WasteOverTimeChart.jsx   # Recharts bar chart over time
        ├── WasteByMachineChart.jsx  # Recharts horizontal ranking
        ├── TopEventsTable.jsx  # Top-5 events table with status badges
        ├── ChatPanel.jsx       # Chat: message list, input, send, typing indicator
        ├── ChatMessage.jsx     # One speech bubble (user / assistant)
        └── ui/
            ├── Card.jsx        # Shared panel wrapper with title + loading/error/empty states
            ├── LoadingState.jsx
            └── ErrorState.jsx
```

---

## Architecture

The dashboard needs two different kinds of data: deterministic JSON for the KPIs, charts, and table; and conversational text for the chat. Both are consumed through a **single API surface** so the frontend only ever talks to one origin.

```
React (Vite dev server)
  ├── KPI cards, charts, table  ──►  GET /api/kpis, /api/waste-over-time, ...
  └── Chat panel                ──►  POST /api/chat
                                       │
                          Vite proxy forwards /api ──► backend gateway (:8000)
```

Every component asks `api/client.js` for data. `client.js` checks one switch (`VITE_USE_MOCKS`) and either returns a fixture from `mocks/mockData.js` or makes a real `fetch` through the Vite proxy. Flipping that one flag is the entire difference between "building offline" and "wired to the backend" — no component code changes.

### Data flow (one KPI, end to end)

1. `App` holds `view` (e.g. `ceo`) and renders `<KpiGrid view={view} />`.
2. `KpiGrid` calls `useKpis(view)` → `useApiResource(() => getKpis(view), [view], { intervalMs })`.
3. `getKpis` → `client.js` → mock fixture (now) or `fetch('/api/kpis?view=ceo')` through the proxy (live).
4. The hook stores `{ data, loading, error }`; `KpiGrid` maps fields to cards; `format.js` turns `18450.5` into `₹18,450.50`.
5. On the refresh interval, or whenever `view` changes, steps 2–4 re-run automatically.

The same pattern repeats for every panel — a thin hook over `useApiResource`, feeding a display component wrapped in `Card`.

---

## Custom hooks

`useApiResource` is the shared engine: hand it a fetch function and a dependency list, get back `{ data, loading, error, refetch }`. It re-fetches when the dependencies change (e.g. the view toggle) and on an optional polling interval. Every data hook is a thin wrapper around it.

```js
export function useKpis(view) {
  return useApiResource(() => getKpis(view), [view], { intervalMs: REFRESH_MS });
}
```

`useChat` is the exception — it holds a growing message array and a session `thread_id` (in a ref, so it survives re-renders), and exposes `send(text)` which posts to the backend and appends the reply.

---

## Components

Components split into **feature** components (in `components/`, specific to this dashboard) and **generic UI** pieces (in `components/ui/`, reusable and app-agnostic). The chart panels and the table all wrap their content in the shared `Card`, which handles the title and the loading / error / empty states in one place.

| Component | Data source | Notes |
|---|---|---|
| `KpiGrid` → `KpiCard` | `useKpis` | 6 cards: total / energy / material waste cost, efficiency ratio, carbon emissions, water cost (water cost pending backend support — see API contract) |
| `WasteOverTimeChart` | `useWasteOverTime` | Recharts bar chart, ₹ over hourly buckets |
| `WasteByMachineChart` | `useWasteByMachine` | Recharts horizontal ranking, sorted descending. Y-axis width and chart height adapt dynamically to machine-name length and count; scrolls internally past ~15 machines |
| `TopEventsTable` | `useTopEvents` | Top-5 events; red total-waste column; status badges |
| `ChatPanel` → `ChatMessage` | `useChat` | Message list, input, send-on-Enter, typing indicator |

No machine names are hardcoded anywhere — machines, rankings, and statuses all come from the data, so the dashboard adapts if the backend adds or removes machines.

---

## View toggle

`App.jsx` owns a single `view` state (`ceo` / `factory` / `department`) and passes it to every data panel. Because each hook lists `view` in its dependencies, switching the toggle refetches the whole dashboard with `?view=<role>`. The frontend stays deliberately dumb about what each role means — the scoping and aggregation happen in backend SQL. Roles are defined once in `config/constants.js`.

> **Open item:** distinguishing *which* factory a Factory Manager manages (and which department for a Department Manager) requires the data to tag rows with factory/department identifiers. Pending confirmation from the backend team. If the data is segmented, the toggle gains dropdowns to pick a specific factory/department; if it's a single simulated factory, the toggle stays a detail-level switch.

---

## Connecting to the backend

The dashboard talks to a single backend gateway on port `8000` via the Vite proxy (configured in `vite.config.js`), so there are no CORS issues in development — the browser only ever sees the Vite origin.

To switch from mocks to live data:

1. Start the backend gateway on `:8000`.
2. Set `VITE_USE_MOCKS=false` in `.env`.
3. Restart `npm run dev`.

### API contract

The frontend is built against these endpoints. `view` is `ceo | factory | department`.

| Endpoint | Returns |
|---|---|
| `GET /api/kpis?view=` | `{ total_waste_cost_inr, energy_waste_cost_inr, material_waste_cost_inr, efficiency_ratio, carbon_emissions_kg_co2, deltas, as_of }` (water cost field pending — see root `README.md` open items) |
| `GET /api/waste-over-time?view=&range=24h` | `{ range, points: [{ bucket, waste_cost_inr }] }` |
| `GET /api/waste-by-machine?view=` | `{ machines: [{ machine_id, waste_cost_inr }] }` (sorted desc) |
| `GET /api/top-events?limit=5` | `{ events: [{ machine_id, timestamp, efficiency_ratio, energy_cost_inr, total_waste_inr, status }] }` |
| `GET /api/machines?view=` | `{ machines: [{ machine_id, status }] }` |
| `POST /api/chat` | body `{ message, thread_id, view }` → `{ reply, thread_id }` |

The exact response shapes are mirrored in `mocks/mockData.js` — that file is the living reference for the contract. When live data renders wrong, compare the real response to the matching mock; the mismatch is the bug.

> **Status:** the FastAPI gateway (`backend/api/`) is **built and live** — all endpoints above serve real data from the DuckDB gold layer, and `/api/chat` forwards to the LangGraph supervisor agent. Run the backend on `:8000`, set `VITE_USE_MOCKS=false` and `VITE_API_BASE=http://localhost:8000/api` (CORS is enabled, so no Vite proxy is needed). Set `VITE_USE_MOCKS=true` to develop the UI with no backend. See the root `README.md` for full-stack setup and `backend/README.md` for gateway details.

---

## Scope

Out of scope for the MVP:

- **Factory map** — excluded for time. The layout reflows so the charts occupy that space; the slot can be reintroduced between the KPI grid and the charts later.
- **Predictive modelling** — the dashboard shows actuals only.
- **Write operations via chat** — the chat is read-only operational Q&A.

---

## Styling

All styling is in `src/index.css` using CSS custom properties for the brand palette:

```css
--c-primary: rgb(19, 140, 143);
--c-deep:    rgb(0, 90, 112);
--c-accent:  rgb(0, 122, 140);
```

The layout is a CSS grid: top bar across the top, then a two-column body — dashboard on the left (KPI row, chart row, table), chat panel on the right. The chat panel's height dynamically matches the dashboard column's measured content height via a `ResizeObserver` in `App.jsx`, rather than being locked to the viewport. The page scrolls normally when content exceeds the viewport, with a small bottom-padding buffer applied automatically (via an `app--needs-padding` class) on short or narrow viewports where content would otherwise touch the edge. Below `1100px` width, the chat panel stacks under the dashboard instead of sitting side-by-side.

---

## Troubleshooting

**Dashboard shows dashes (`—`) everywhere**

With `VITE_USE_MOCKS=false`, the backend gateway isn't reachable or isn't returning the expected shape. Confirm the gateway runs on `:8000`, or set `VITE_USE_MOCKS=true` to fall back to fixtures.

**Edited `.env` but nothing changed**

`.env` is only read at server start. Stop (`Ctrl+C`) and re-run `npm run dev`.

**Port 5173 in use / app opens on 5174**

Harmless — Vite picks the next free port and prints the real URL. Usually means another `npm run dev` is still running in a different terminal.

**Charts or table empty but no error**

The API returned an empty array. The `Card` wrapper shows "No data yet." for empty data and the error state only for actual failures — so an empty panel means the query genuinely returned nothing.

**Chat only replies with `(mock) You asked: ...`**

That's the mock backend answering. Real agent responses require `VITE_USE_MOCKS=false` and the live `/api/chat` endpoint.

---

## Future Changes

Identified during development but out of scope for the MVP — candidates for future enhancement. Listed here so the reasoning isn't lost and future work has clear starting points.

**Mobile-responsive layout**
The dashboard currently adapts down to a `1100px` breakpoint (chat panel stacks under the dashboard instead of sitting side-by-side), but true phone-width layouts haven't been tested or tuned. Worth doing because the target audience — senior executives and facility owners — are realistically checking metrics between meetings on a phone, not always at a desk. Would need its own breakpoint(s) below `1100px`, likely simplifying the KPI grid to a single column and revisiting chart sizing for narrow screens.

**Login / authentication**
There's currently no access control — anyone with the URL sees the dashboard, and the CEO / Factory Manager / Department Manager toggle is just a UI switch anyone can click, not tied to who's actually logged in. For a real deployment with genuine financial data, access should be gated, and the existing role toggle should map to an authenticated user's actual role rather than being self-selected. Needs a decision on auth approach (simple password gate vs. proper user accounts) before implementation.

**Chat streaming**
`/api/chat` currently returns one complete response rather than streaming tokens as they're generated, so replies appear all at once after a delay rather than word-by-word. Streaming would make the assistant feel more responsive, especially for longer answers, and is a common expectation for chat interfaces at this point. Requires both a backend change (streaming response support in the FastAPI gateway) and a frontend change (incrementally rendering chunks in `ChatPanel`/`ChatMessage`).

**Frontend automated test suite**
No automated tests currently exist on the frontend. Highest-value targets identified: formatters in `utils/format.js` (e.g. `formatINR`, `formatCO2`), `scopeParams()` in the API client, the view-toggle/scope logic, the mock/live switch (`VITE_USE_MOCKS`), and the `useChat` hook. Would use Vitest + React Testing Library. Matters most before any further refactors, since right now every layout/logic change is verified by hand.

**Factory map visual**
Explicitly deferred in the original project scope due to time constraints. The dashboard currently reflows the chart row to fill the space where a factory floor-plan/map view was originally planned. Would give senior management a spatial view of where waste is occurring, complementing the existing charts and tables.

**API field-name alignment**
A few frontend/backend field-name mismatches have surfaced during development (e.g. `{id, name}` vs `{facility_id, label}` for scope dropdowns) and were resolved case-by-case as found. Worth a dedicated pass once all endpoints are stable to confirm every response shape matches what `mocks/mockData.js` documents as the contract, so future backend changes don't silently break the frontend.