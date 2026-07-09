"""Dashboard GET endpoints. Responses match frontend/src/mocks/mockData.js field-for-field.

Waste convention: waste_cost = estimated_power_waste_cost_inr + material_waste_cost_inr.
Confirmed by both designers: `energy_waste_cost_inr` = estimated_power_waste_cost_inr
(EXCESS power waste, not total power cost). material_waste_cost_inr is excess by nature.

NOTE (data designer): wastes should eventually be split further — electricity / WATER /
material, all excess-only. Water waste has no column in the gold layer yet (the builder
computes operational_water_cost_inr = total, not excess). Adding it needs a data-side
change in build_gold_layer.py + a frontend card. Tracked as an open cross-team item.
"""
from fastapi import APIRouter, Query

from api.db import GOLD, connect, max_timestamp, scope_where

router = APIRouter(prefix="/api")

# Per-row total waste (energy waste + material waste).
_WASTE = "(estimated_power_waste_cost_inr + material_waste_cost_inr)"

# Shared scope query params — accepted by every endpoint per the frontend contract.
_View = Query(default="ceo")
_Facility = Query(default=None)
_Department = Query(default=None)


@router.get("/kpis")
def kpis(view: str = _View, facility_id: str = _Facility, department_id: str = _Department):
    where, params = scope_where(facility_id, department_id)
    sql = f"""
        SELECT
            COALESCE(SUM(estimated_power_waste_cost_inr), 0) AS energy_waste,
            COALESCE(SUM(material_waste_cost_inr), 0)        AS material_waste,
            COALESCE(SUM(estimated_water_waste_cost_inr), 0)  AS water_waste,
            COALESCE(AVG(efficiency_ratio), 0)               AS efficiency_ratio,
            COALESCE(SUM(carbon_emissions_kg_co2), 0)        AS carbon_emissions
        FROM {GOLD} {where}
    """
    with connect() as conn:
        energy, material, water, eff, carbon = conn.execute(sql, params).fetchone()
        as_of = max_timestamp(conn)
    return {
        "total_waste_cost_inr": round(energy + material + water, 2),
        "energy_waste_cost_inr": round(energy, 2),
        "material_waste_cost_inr": round(material, 2),
        "water_waste_cost_inr": round(water, 2),
        "efficiency_ratio": round(eff, 3),
        "carbon_emissions_kg_co2": round(carbon, 2),
        # deltas: frontend designer plans to drop the delta UI (no history yet). Data will
        # accumulate over time (new sensor files land), so real period-over-period deltas
        # become computable later. Returning neutral 0.0 keeps the field non-breaking meanwhile.
        "deltas": {
            "total_waste_cost_inr": 0.0,
            "energy_waste_cost_inr": 0.0,
            "material_waste_cost_inr": 0.0,
            "water_waste_cost_inr": 0.0,
            "efficiency_ratio": 0.0,
        },
        "as_of": as_of,
    }


def _range_interval(range_: str) -> str:
    """Map a range token to a DuckDB INTERVAL. Defaults to 24 hours."""
    return {"24h": "24 hours", "7d": "7 days", "30d": "30 days"}.get(range_, "24 hours")


@router.get("/waste-over-time")
def waste_over_time(
    view: str = _View,
    facility_id: str = _Facility,
    department_id: str = _Department,
    range: str = Query(default="24h"),
):
    where, params = scope_where(facility_id, department_id)
    # Window anchors on MAX(timestamp), not now() — data is a fixed snapshot.
    cond = f"{where} AND" if where else "WHERE"
    sql = f"""
        SELECT date_trunc('hour', timestamp) AS bucket,
               ROUND(SUM({_WASTE}), 2)        AS waste_cost_inr
        FROM {GOLD}
        {cond} timestamp >= (SELECT MAX(timestamp) FROM {GOLD}) - INTERVAL '{_range_interval(range)}'
        GROUP BY bucket
        ORDER BY bucket
    """
    with connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    points = [{"bucket": b.isoformat(), "waste_cost_inr": w} for b, w in rows]
    return {"range": range, "points": points}


@router.get("/waste-by-machine")
def waste_by_machine(view: str = _View, facility_id: str = _Facility, department_id: str = _Department):
    where, params = scope_where(facility_id, department_id)
    sql = f"""
        SELECT machine_id, ROUND(SUM({_WASTE}), 2) AS waste_cost_inr
        FROM {GOLD} {where}
        GROUP BY machine_id
        ORDER BY waste_cost_inr DESC
    """
    with connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return {"machines": [{"machine_id": m, "waste_cost_inr": w} for m, w in rows]}


@router.get("/top-events")
def top_events(
    view: str = _View,
    facility_id: str = _Facility,
    department_id: str = _Department,
    limit: int = Query(default=5, ge=1, le=100),
):
    where, params = scope_where(facility_id, department_id)
    sql = f"""
        SELECT machine_id,
               timestamp,
               ROUND(efficiency_ratio, 3)          AS efficiency_ratio,
               ROUND(operational_power_cost_inr, 2) AS energy_cost_inr,
               ROUND({_WASTE}, 2)                   AS total_waste_inr,
               status
        FROM {GOLD} {where}
        ORDER BY total_waste_inr DESC
        LIMIT ?
    """
    with connect() as conn:
        rows = conn.execute(sql, [*params, limit]).fetchall()
    events = [
        {
            "machine_id": r[0],
            "timestamp": r[1].isoformat(),
            "efficiency_ratio": r[2],
            "energy_cost_inr": r[3],
            "total_waste_inr": r[4],
            "status": r[5],
        }
        for r in rows
    ]
    return {"events": events}


@router.get("/machines")
def machines(view: str = _View, facility_id: str = _Facility, department_id: str = _Department):
    where, params = scope_where(facility_id, department_id)
    # Latest status per machine.
    sql = f"""
        SELECT machine_id, status FROM (
            SELECT machine_id, status,
                   ROW_NUMBER() OVER (PARTITION BY machine_id ORDER BY timestamp DESC) AS rn
            FROM {GOLD} {where}
        ) WHERE rn = 1
        ORDER BY machine_id
    """
    with connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return {"machines": [{"machine_id": m, "status": s} for m, s in rows]}


# --- Scope-option endpoints -------------------------------------------------
# Shapes confirmed against frontend mockData.js (dropdowns bind to these):
#   facilities:  {facility_id, label}
#   departments: {department_id, label, facility_id}
# No name lookup table exists (data designer), so `label` is derived from the id:
# "CHENNAI_RECYCLING_PLANT" -> "Chennai Recycling Plant".

def _label(raw: str) -> str:
    return " ".join(w.capitalize() for w in raw.split("_"))


@router.get("/facilities")
def facilities():
    with connect() as conn:
        rows = conn.execute(f"SELECT DISTINCT facility_id FROM {GOLD} ORDER BY 1").fetchall()
    return {"facilities": [{"facility_id": f, "label": _label(f)} for (f,) in rows]}


@router.get("/departments")
def departments(facility_id: str = _Facility):
    where, params = scope_where(facility_id, None)
    sql = f"SELECT DISTINCT department_id, facility_id FROM {GOLD} {where} ORDER BY 1"
    with connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    # facility_id on each row — the dept dropdown filters by selected facility.
    return {
        "departments": [
            {"department_id": d, "label": _label(d), "facility_id": fac} for d, fac in rows
        ]
    }
