import duckdb
from pathlib import Path

# Dynamically resolve the directories based on this script's location
CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent.parent

RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"
DB_DIR = PROJECT_ROOT / "data" / "database"

# Ensure the database directory exists
DB_DIR.mkdir(parents=True, exist_ok=True)

# Define exact file paths
DB_FILE = DB_DIR / "operational_twin.db"
ERP_FILE = RAW_DATA_DIR / "erp_daily_rates_inr.csv"
SENSOR_FILE = RAW_DATA_DIR / "sensor_data.json"

def build_operational_twin_db():
    print("Initializing DuckDB Operational Twin Database...")
    print(f"Target Database location: {DB_FILE}")
    
    # 1. Connect to the persistent database file in the data/database/ folder
    # We use str() because duckdb expects string paths, not Path objects
    conn = duckdb.connect(str(DB_FILE))

    # 2. Ingest the Silver Layer: ERP Batch Data (CSV)
    print(f"Loading ERP Batch Data from: {ERP_FILE.name}...")
    conn.execute(f"""
        CREATE OR REPLACE TABLE erp_rates AS 
        SELECT * FROM read_csv_auto('{str(ERP_FILE)}');
    """)

    # 3. Ingest the Silver Layer: IoT Streaming Data (JSON Array)
    print(f"Loading IoT Telemetry Data from: {SENSOR_FILE.name}...")
    conn.execute(f"""
        CREATE OR REPLACE TABLE sensor_telemetry AS 
        SELECT * FROM read_json_auto('{str(SENSOR_FILE)}');
    """)

    # 4. Build the Gold Layer: The Business Logic Join
    print("Constructing Gold Layer (Financial Impact Analytics)...")
    gold_layer_sql = """
        CREATE OR REPLACE TABLE gold_operational_metrics AS
        SELECT 
            s.timestamp,
            CAST(s.timestamp AS DATE) as operation_date,
            s.machine_id,
            s.status,
            s.metrics.power_consumption_kw AS power_kw,
            s.metrics.material_intake_kg AS material_in_kg,
            s.metrics.material_output_kg AS material_out_kg,
            e.electricity_rate_per_kwh_inr AS current_electricity_rate,
            
            ROUND((s.metrics.power_consumption_kw * e.electricity_rate_per_kwh_inr), 2) AS operational_cost_inr,
            
            ROUND(
                CASE 
                    WHEN s.status = 'CRITICAL_POWER_WASTE' THEN ((s.metrics.power_consumption_kw - 300) * e.electricity_rate_per_kwh_inr)
                    ELSE 0 
                END, 2
            ) AS estimated_waste_cost_inr,
            
            ROUND(((s.metrics.material_intake_kg - s.metrics.material_output_kg) * e.raw_pet_cost_per_kg_inr), 2) AS material_waste_cost_inr

        FROM sensor_telemetry s
        LEFT JOIN erp_rates e ON CAST(s.timestamp AS DATE) = CAST(e.date AS DATE);
    """
    conn.execute(gold_layer_sql)

    # 5. Verify the Gold Layer
    print("\n--- Gold Layer Sample Data ---")
    result = conn.execute("""
        SELECT timestamp, machine_id, status, power_kw, estimated_waste_cost_inr, material_waste_cost_inr 
        FROM gold_operational_metrics 
        ORDER BY estimated_waste_cost_inr DESC 
        LIMIT 5;
    """).fetchdf()
    
    print(result)
    print(f"\nSuccess! '{DB_FILE.name}' is ready for the AI Agent.")
    conn.close()

if __name__ == "__main__":
    # Safety Check: Ensure the raw files actually exist before trying to build the database
    if not ERP_FILE.exists():
        print(f"Error: Could not find {ERP_FILE}. Please run erp_batch_gen.py first.")
    elif not SENSOR_FILE.exists():
        print(f"Error: Could not find {SENSOR_FILE}. Please run sensor_stream.py first.")
    else:
        build_operational_twin_db()