# AI Operational Twin

An industrial analytics platform for a PET-recycling operation. It generates synthetic ERP +
IoT sensor data, enriches it into a financial-impact "gold layer" in DuckDB, serves it through
a LangGraph agent + FastAPI gateway, and visualises it in a React dashboard with an
AI chat assistant.

Three layers, end to end:

| Layer | What it does | Docs |
|---|---|---|
| **Data pipeline** (`src/`, `data/`) | Generates ERP/sensor data, builds the `gold_operational_metrics` DuckDB table | [below](#data-pipeline) |
| **Backend** (`backend/`) | A LangGraph agent (DuckDB + web tools, HITL on writes) and a FastAPI gateway serving dashboard + chat | [`backend/README.md`](backend/README.md) |
| **Frontend** (`frontend/`) | React + Vite dashboard: KPIs, waste charts, top-events, scope dropdowns, chat | [`frontend/README.md`](frontend/README.md) |

---

## Contributors

| Name | Role | University |
|---|---|---|
| [Udaya Bhandarkar](https://www.linkedin.com/in/udaya-bhandarkar/) | Team Lead & Architect | University of Warwick |
| [Emma Leahy](https://www.linkedin.com/in/emma-leahy-443b36235) | Frontend & UI Developer | University of Warwick |
| [Saad Waqas](https://www.linkedin.com/in/saad-bin-waqas-36597325b/) | AI & Orchestration Engineer | King Fahd University of Petroleum and Minerals |
| [Krisztina Hermán](https://www.linkedin.com/in/krisztina-hermán) | Business Analyst & QA | Corvinus University of Budapest |
| [Nikola Jevric](https://www.linkedin.com/in/jevricnikola) | Documentation & Project Management | Corvinus University of Budapest |

---

## Architecture

```text
 ERP generator ─► erp_daily_rates_inr.csv ─┐
                                           ├─► DuckDB gold_operational_metrics
 Sensor stream ─► sensor_data_*.json ──────┘              │
                                                          ▼
                                          FastAPI gateway (backend/api, :8000)
                                          ├─ GET /api/kpis, /waste-*, /machines, …  (reads gold table)
                                          └─ POST /api/chat ─► LangGraph agent ─► DuckDB / web tools
                                                          │
                                                          ▼
                                          React dashboard (frontend, :5173)
```

The dashboard reads the gold table through the gateway's REST endpoints; the chat forwards to
the LangGraph agents, which query the same DuckDB.

---

## Repository layout

```
ai_operational_twin/
├── src/                    # Data pipeline (ERP + sensor generators, gold-layer builder)
│   ├── data_pipeline/
│   └── ai_engine/
├── data/
│   ├── raw/                # Generated ERP csv + sensor json (inputs)
│   └── database/           # Built DuckDB file (gitignored — rebuild locally)
├── backend/                # LangGraph agent + FastAPI gateway                → backend/README.md
├── frontend/               # React + Vite dashboard                           → frontend/README.md
└── README.md               # You are here
```

---

## Quickstart (full stack)

Run the three layers in order. Each sub-README has the deep detail; this is the happy path.

### Prerequisites
- Python 3.11+ and [`uv`](https://github.com/astral-sh/uv)
- Node.js 18+ and npm
- An LLM provider API key (Anthropic / Groq / Mistral) — needed for **chat only**; the dashboard works without one

### 1. Build the data (DuckDB gold layer)

```bash
python src/data_pipeline/erp_batch_gen.py      # ERP rates  → data/raw/erp_daily_rates_inr.csv
python src/data_pipeline/sensor_stream.py      # Sensor data → data/raw/sensor_data_*.json  (Ctrl+C to stop)
python src/data_pipeline/build_gold_layer.py   # Builds data/database/operational_twin.db
```

Re-run `build_gold_layer.py` whenever new sensor files land — it re-ingests all of them.

### 2. Start the backend gateway (port 8000)

Full setup (venv, env keys, agents) is in [`backend/README.md`](backend/README.md). Minimal:

```bash
cd backend
uv venv .venv --python 3.11
uv pip install -e .
cp .env.example .env          # fill in your provider key (chat only)
.venv/Scripts/python.exe -m uvicorn api.app:app --port 8000
```

Verify: `curl http://localhost:8000/health` → `{"status":"ok"}`.

> The gateway serves the dashboard endpoints and forwards `/api/chat` to the LangGraph agents.
> To explore the agents directly in LangGraph Studio, use `langgraph dev` instead — see the backend README.

### 3. Start the frontend (port 5173)

Full detail in [`frontend/README.md`](frontend/README.md). Minimal:

```bash
cd frontend
npm install
cp .env.example .env
# in .env: VITE_USE_MOCKS=false and VITE_API_BASE=http://localhost:8000/api
npm run dev
```

Open the printed URL (`http://localhost:5173`). Dashboard renders live data; chat needs a valid
provider key in `backend/.env`. To develop the UI with no backend, set `VITE_USE_MOCKS=true`.

---

## Documentation

| Doc | Covers |
|---|---|
| [`backend/README.md`](backend/README.md) | Agent, middleware, tools, HITL, evals/CI, the **API gateway** (endpoints, scope params, CORS), config, troubleshooting |
| [`backend/evals/README.md`](backend/evals/README.md) | **Running the evals** — setup from a fresh clone, uploading the QA questions, and reading the results in LangSmith |
| [`frontend/README.md`](frontend/README.md) | Components, hooks, the mock/live switch, view toggle, styling, connecting to the backend |

---

## Data pipeline

The `src/` layer produces the single source of truth: the `gold_operational_metrics` table.

| Component | File | Output |
|---|---|---|
| ERP batch generator | `src/data_pipeline/erp_batch_gen.py` | `data/raw/erp_daily_rates_inr.csv` (electricity/water/PET rates) |
| Sensor stream generator | `src/data_pipeline/sensor_stream.py` | `data/raw/sensor_data_*.json` (machine telemetry) |
| Gold-layer builder | `src/data_pipeline/build_gold_layer.py` | `data/database/operational_twin.db` |

The builder loads both sources into DuckDB (`erp_rates`, `sensor_telemetry`), joins them by date,
and computes operational costs + waste. Data keeps arriving as more sensor files land; the
`sensor_data_*.json` wildcard ingests all of them on each rebuild.

### `gold_operational_metrics` schema

| Column | Description |
|---|---|
| timestamp / operation_date | Telemetry time + derived date |
| facility_id / department_id / line_id / machine_id | Location + machine hierarchy |
| status | `NORMAL` / `CRITICAL_POWER_WASTE` |
| power_kw / water_liters | Resource consumption |
| material_in_kg / material_out_kg / efficiency_ratio | Material throughput |
| current_electricity_rate / current_water_rate | ERP rates (joined) |
| operational_power_cost_inr / operational_water_cost_inr | Total resource cost (not waste) |
| estimated_power_waste_cost_inr | **Excess** power cost (power over the 300 kW threshold) |
| estimated_water_waste_cost_inr | **Excess** water cost (water over the 25 L threshold) |
| material_waste_cost_inr | Material lost (`in − out`) × PET rate |
| carbon_emissions_kg_co2 | Estimated carbon |

Waste convention used across the stack: total waste = **excess only**, summing power waste,
water waste, and material waste. See `build_gold_layer.py` for the exact SQL.

---

## Project status

- ✅ Data pipeline → DuckDB gold layer
- ✅ LangGraph agent backend (DuckDB + web tools, single reasoning loop) + FastAPI gateway
- ✅ React dashboard wired to live endpoints (KPIs, charts, tables, scope dropdowns)
- ✅ Chat end-to-end through the gateway (Markdown tables rendered in the UI)
- ✅ Eval suite (116 QA questions) — runnable against the tester's dataset; see [`backend/evals/README.md`](backend/evals/README.md)
- ✅ Waste model — power, water, and material waste (all excess-only) summed into total waste
- ⏳ **Chat streaming** — the gateway returns one complete response; no token-by-token streaming yet


