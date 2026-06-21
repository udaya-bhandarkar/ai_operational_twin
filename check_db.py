import duckdb
import pandas as pd
from pathlib import Path

# Locate your database file
DB_FILE = Path(__file__).resolve().parent / "data" / "database" / "operational_twin.db"

def inspect_database():
    print(f"Connecting to {DB_FILE.name}...\n")
    
    # Open connection in read-only mode for safety
    conn = duckdb.connect(str(DB_FILE), read_only=True)

    try:
        # 1. See all tables currently in the database
        print("--- TABLES IN DATABASE ---")
        tables = conn.execute("SHOW TABLES;").df()
        print(tables.to_string(index=False))
        print("\n")

        # 2. Check the schema of the Gold Layer
        print("--- GOLD LAYER SCHEMA ---")
        schema = conn.execute("DESCRIBE gold_operational_metrics;").df()
        print(schema[['column_name', 'column_type']].to_string(index=False))
        print("\n")

        query = """
            SELECT *
            FROM gold_operational_metrics 
            LIMIT 10;
        """
        data = conn.execute(query).df()
        print(data.to_string(index=False))

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    # Pandas display settings to ensure columns don't get hidden
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', 1000)
    inspect_database()