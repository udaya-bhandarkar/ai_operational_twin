import duckdb
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent.parent

RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"
DB_DIR = PROJECT_ROOT / "data" / "database"
DB_DIR.mkdir(parents=True, exist_ok=True)

DB_FILE = DB_DIR / "operational_twin.db"
ERP_FILE = RAW_DATA_DIR / "erp_daily_rates_inr.csv"
SENSOR_FILE = RAW_DATA_DIR / "sensor_data.json"

def build_operational_twin_db():
    print("Initializing DuckDB Operational Twin Database...")
    conn = duckdb.connect(str(DB_FILE))

    print(f"Loading ERP Batch Data from: {ERP_FILE.name}...")
    conn.execute(f"""
        CREATE OR REPLACE TABLE erp_rates AS 
        SELECT * FROM read_csv_auto('{str(ERP_FILE)}');
    """)

    print(f"Loading IoT Telemetry Data from: {SENSOR_FILE.name}...")
    conn.execute(f"""
        CREATE OR REPLACE TABLE sensor_telemetry AS 
        SELECT * FROM read_json_auto('{str(SENSOR_FILE)}');
    """)

    print("Constructing Gold Layer (Financial Impact Analytics)...")
    gold_layer_sql = """
        CREATE OR REPLACE TABLE gold_operational_metrics AS
        SELECT 
            s.timestamp,
            CAST(s.timestamp AS DATE) as operation_date,
            
            -- NEW: Extracted Hierarchy
            s.facility_id,
            s.department_id,
            s.line_id,
            s.machine_id,
            s.status,
            
            -- Extracted Metrics
            s.metrics.power_consumption_kw AS power_kw,
            s.metrics.water_consumption_liters AS water_liters, -- NEW
            s.metrics.material_intake_kg AS material_in_kg,
            s.metrics.material_output_kg AS material_out_kg,
            s.metrics.efficiency_ratio AS efficiency_ratio,     -- NEW
            
            -- ERP Rates
            e.electricity_rate_per_kwh_inr AS current_electricity_rate,
            e.water_rate_per_liter_inr AS current_water_rate,   -- NEW
            
            -- Financial Impact Calculations
            ROUND((s.metrics.power_consumption_kw * e.electricity_rate_per_kwh_inr), 2) AS operational_power_cost_inr,
            ROUND((s.metrics.water_consumption_liters * e.water_rate_per_liter_inr), 2) AS operational_water_cost_inr,
            
            ROUND(
                CASE 
                    WHEN s.status = 'CRITICAL_POWER_WASTE' THEN ((s.metrics.power_consumption_kw - 300) * e.electricity_rate_per_kwh_inr)
                    ELSE 0 
                END, 2
            ) AS estimated_power_waste_cost_inr,
            
            ROUND(((s.metrics.material_intake_kg - s.metrics.material_output_kg) * e.raw_pet_cost_per_kg_inr), 2) AS material_waste_cost_inr

        FROM sensor_telemetry s
        LEFT JOIN erp_rates e ON CAST(s.timestamp AS DATE) = CAST(e.date AS DATE);
    """
    conn.execute(gold_layer_sql)

    print("\n--- Gold Layer Sample Data ---")
    result = conn.execute("""
        SELECT 
            department_id, 
            machine_id, 
            efficiency_ratio, 
            water_liters, 
            estimated_power_waste_cost_inr 
        FROM gold_operational_metrics 
        ORDER BY estimated_power_waste_cost_inr DESC 
        LIMIT 5;
    """).fetchdf()
    
    print(result)
    print(f"\nSuccess! '{DB_FILE.name}' is fully updated with Water, Material Traceability, and Facility Hierarchy.")
    conn.close()

if __name__ == "__main__":
    if not ERP_FILE.exists():
        print(f"Error: Could not find {ERP_FILE}. Please run erp_batch_gen.py first.")
    elif not SENSOR_FILE.exists():
        print(f"Error: Could not find {SENSOR_FILE}. Please run sensor_stream.py first.")
    else:
        build_operational_twin_db()