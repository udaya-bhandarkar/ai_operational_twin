# AI Operational Twin

## Overview

AI Operational Twin is a lightweight industrial analytics simulation that combines:

- ERP/business data (costs and rates)
- IoT machine telemetry
- DuckDB analytics

The system generates synthetic manufacturing data, enriches operational events with financial information, and produces a Gold Layer table for operational cost and waste analysis.

---

## Architecture

```text
ERP Batch Generator
        │
        ▼
erp_daily_rates_inr.csv
        │
        ▼
    erp_rates
        │
        │
        ├──────────────┐
        │              │
        ▼              │
                      JOIN
        ▲              │
        │              ▼
sensor_telemetry ──► gold_operational_metrics
        ▲
        │
sensor_data.json
        ▲
        │
Sensor Stream Generator
```

---

## Project Components

### 1. ERP Batch Generator

**File**

```text
src/data_pipeline/erp_batch_gen.py
```

Generates daily ERP/business records including:

- Electricity cost per kWh
- Raw PET material cost
- Finished thread selling price
- Daily maintenance cost

**Output**

```text
data/raw/erp_daily_rates_inr.csv
```

---

### 2. Sensor Stream Generator

**File**

```text
src/data_pipeline/sensor_stream.py
```

Simulates machine telemetry for manufacturing equipment.

Monitored machines:

- PET_SHREDDER_01
- EXTRUDER_UNIT_01
- SPINNING_LINE_01

Generated metrics:

- Power consumption
- Material intake
- Material output
- Efficiency ratio
- Operational status

**Output**

```text
data/raw/sensor_data.json
```

---

### 3. Gold Layer Builder

**File**

```text
src/data_pipeline/build_gold_layer.py
```

Loads both data sources into DuckDB and creates the final analytics table.

Operations performed:

1. Load ERP CSV data
2. Load sensor JSON data
3. Join datasets by operation date
4. Calculate operational costs
5. Calculate estimated energy waste costs
6. Calculate material waste costs

**Output Database**

```text
data/database/operational_twin.db
```

---

### 4. AI Agent Verification

**File**

```text
src/ai_engine/agent.py
```

Connects to DuckDB and retrieves:

- Top 5 highest waste events
- Machine waste rankings
- Operational insights

---

# Data Model

## Silver Layer

### erp_rates

| Column | Description |
|----------|-------------|
| date | ERP business date |
| electricity_rate_per_kwh_inr | Electricity price (INR/kWh) |
| raw_pet_cost_per_kg_inr | Raw PET material cost |
| finished_thread_price_per_kg_inr | Product selling price |
| daily_facility_maintenance_inr | Daily maintenance cost |

---

### sensor_telemetry

| Column | Description |
|----------|-------------|
| timestamp | Event timestamp |
| event_type | Event type |
| machine_id | Machine identifier |
| metrics | Nested telemetry metrics |
| status | Operational state |

#### metrics structure

| Field | Description |
|---------|-------------|
| power_consumption_kw | Machine power draw |
| material_intake_kg | Input material |
| material_output_kg | Output material |
| efficiency_ratio | Output/Input ratio |

---

## Gold Layer

### gold_operational_metrics

This is the final analytics table used by downstream consumers.

| Column | Description |
|----------|-------------|
| timestamp | Telemetry timestamp |
| operation_date | Extracted operation date |
| machine_id | Machine identifier |
| status | Machine status |
| power_kw | Power consumption |
| material_in_kg | Material input |
| material_out_kg | Material output |
| current_electricity_rate | ERP electricity rate |
| operational_cost_inr | Power cost |
| estimated_waste_cost_inr | Excess energy waste cost |
| material_waste_cost_inr | Material loss cost |

---

# Cost Calculations

### Operational Cost

```sql
power_kw * electricity_rate
```

### Estimated Energy Waste Cost

```sql
CASE
    WHEN status = 'CRITICAL_POWER_WASTE'
    THEN (power_kw - 300) * electricity_rate
    ELSE 0
END
```

### Material Waste Cost

```sql
(material_in_kg - material_out_kg)
    * raw_pet_cost_per_kg_inr
```

---

# Example Output

| timestamp | machine_id | status | power_kw | estimated_waste_cost_inr |
|------------|------------|---------|-----------|--------------------------|
| 2026-06-08T10:12:51Z | SPINNING_LINE_01 | CRITICAL_POWER_WASTE | 307.95 | 75.43 |

Interpretation:

- Machine exceeded the 300 kW threshold.
- Additional electricity usage is treated as waste.
- Waste is converted into monetary impact using ERP electricity rates.

---

# Running the Project

## Step 1: Generate ERP Data

```bash
python src/data_pipeline/erp_batch_gen.py
```

---

## Step 2: Generate Sensor Data

Run the stream and stop it with `Ctrl+C` when enough events have been generated.

```bash
python src/data_pipeline/sensor_stream.py
```

---

## Step 3: Build the Gold Layer

```bash
python src/data_pipeline/build_gold_layer.py
```

This creates:

```text
data/database/operational_twin.db
```

---

## Step 4: Verify Results

```bash
python src/ai_engine/agent.py
```

Example output:

```text
Top 5 Highest Waste Events (in INR):

timestamp              machine_id         power_kw   rate_inr   waste_cost
---------------------------------------------------------------------------
2026-06-08T10:15:00Z   PET_SHREDDER_01    548.20     9.81       2435.84
...
```

---

# Technology Stack

- Python
- DuckDB
- CSV
- JSON
- Pathlib

---

# Future Enhancements

- Real-time streaming ingestion
- Dashboard visualization
- Predictive maintenance models
- LLM-powered operational assistant
- Machine-level KPI summaries
- Facility-level analytics
- Automated anomaly detection

---

# Final Output

The primary output of the project is:

```text
gold_operational_metrics
```

This Gold Layer table serves as the single source of truth for operational cost, waste, and efficiency analytics.