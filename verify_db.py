import duckdb
from pathlib import Path

# Locate the database file
db_path = Path("data/database/operational_twin.db")

if not db_path.exists():
    print("Database not found! Please ensure you ran build_gold_layer.py")
else:
    # Connect and run a quick verification query
    conn = duckdb.connect(str(db_path), read_only=True)
    
    print("Top 5 Highest Waste Events (in INR):")
    
    query = """
        SELECT 
            timestamp, 
            machine_id, 
            power_kw, 
            current_electricity_rate as rate_inr, 
            estimated_waste_cost_inr as waste_cost
        FROM gold_operational_metrics 
        WHERE estimated_waste_cost_inr > 0
        ORDER BY estimated_waste_cost_inr DESC 
        LIMIT 5;
    """
    
    # Fetch and print the results as a clean table
    print(conn.execute(query).fetchdf())
    conn.close()