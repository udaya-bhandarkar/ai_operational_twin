import csv
import random
from datetime import datetime, timedelta
from pathlib import Path

# Dynamically resolve the target directory
CURRENT_DIR = Path(__file__).resolve().parent
RAW_DATA_DIR = CURRENT_DIR.parent.parent / "data" / "raw"
RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)

# Static ERP rates (in INR)
STATIC_ELECTRICITY_RATE = 9.00           # Midpoint of (7.5, 10.5)
STATIC_WATER_RATE = 0.85                 # Midpoint of (0.5, 1.2)
STATIC_RAW_PET_COST = 41.50              # Midpoint of (35.0, 48.0)
STATIC_FINISHED_THREAD_PRICE = 190.00    # Midpoint of (160.0, 220.0)
STATIC_DAILY_FACILITY_MAINTENANCE = 65000.00 # Midpoint of (40000.0, 90000.0)

def generate_erp_batch(days_to_generate=30, filename="erp_daily_rates_inr.csv"):
    output_file = RAW_DATA_DIR / filename
    
    # NEW: Added water_rate_per_liter_inr
    headers = [
        "date", 
        "electricity_rate_per_kwh_inr", 
        "water_rate_per_liter_inr", 
        "raw_pet_cost_per_kg_inr", 
        "finished_thread_price_per_kg_inr",
        "daily_facility_maintenance_inr"
    ]
    
    end_date = datetime.utcnow().date()
    start_date = end_date - timedelta(days=days_to_generate)
    
    print(f"Generating ERP batch data from {start_date} to {end_date} in INR...")
    
    records = []
    
    for i in range(days_to_generate + 1):
        current_date = start_date + timedelta(days=i)
        
        electricity_rate = STATIC_ELECTRICITY_RATE
        water_rate = STATIC_WATER_RATE
        raw_pet_cost = STATIC_RAW_PET_COST
        thread_price = STATIC_FINISHED_THREAD_PRICE
        maintenance_cost = STATIC_DAILY_FACILITY_MAINTENANCE
        
        records.append({
            "date": current_date.isoformat(),
            "electricity_rate_per_kwh_inr": electricity_rate,
            "water_rate_per_liter_inr": water_rate,
            "raw_pet_cost_per_kg_inr": raw_pet_cost,
            "finished_thread_price_per_kg_inr": thread_price,
            "daily_facility_maintenance_inr": maintenance_cost
        })
        
    with open(output_file, mode='w', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=headers)
        writer.writeheader()
        writer.writerows(records)
        
    print(f"Success! ERP data saved to {output_file}")
    print(f"Total records: {len(records)}")

if __name__ == "__main__":
    generate_erp_batch(days_to_generate=30)