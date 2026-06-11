import csv
import random
from datetime import datetime, timedelta
from pathlib import Path

# Dynamically resolve the target directory
CURRENT_DIR = Path(__file__).resolve().parent
RAW_DATA_DIR = CURRENT_DIR.parent.parent / "data" / "raw"
RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)

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
        
        electricity_rate = round(random.uniform(7.5, 10.5), 2)
        water_rate = round(random.uniform(0.5, 1.2), 2)  # NEW: Water costs ₹0.5 to ₹1.2 per liter
        raw_pet_cost = round(random.uniform(35.0, 48.0), 2)     
        thread_price = round(random.uniform(160.0, 220.0), 2)   
        maintenance_cost = round(random.uniform(40000.0, 90000.0), 2)
        
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