import json
import sys
import time
import random
from datetime import datetime
from pathlib import Path

# Dynamically resolve the target directory relative to this script's location
# Navigates from src/data_pipeline -> src -> ai_operational_twin -> data/raw
CURRENT_DIR = Path(__file__).resolve().parent
RAW_DATA_DIR = CURRENT_DIR.parent.parent / "data" / "raw"

# Automatically create the directories if they don't exist
RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)

MACHINES = ["PET_SHREDDER_01", "EXTRUDER_UNIT_01", "SPINNING_LINE_01"]
# Set the output file path to the raw data directory
OUTPUT_FILE = RAW_DATA_DIR / "sensor_data.json"

def generate_sensor_event(machine_id):
    power_kw = random.uniform(280.0, 310.0)
    is_choking = random.random() < 0.10
    
    if is_choking:
        power_kw = random.uniform(450.0, 550.0)
        
    material_in_kg = random.uniform(45.0, 50.0) 
    efficiency = random.uniform(0.60, 0.75) if is_choking else random.uniform(0.95, 0.99)
    material_out_kg = material_in_kg * efficiency
    status = "CRITICAL_POWER_WASTE" if power_kw > 300 else "NORMAL"

    event = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "event_type": "machine_telemetry",
        "machine_id": machine_id,
        "metrics": {
            "power_consumption_kw": round(power_kw, 2),
            "material_intake_kg": round(material_in_kg, 2),
            "material_output_kg": round(material_out_kg, 2),
            "efficiency_ratio": round(efficiency, 3)
        },
        "status": status
    }
    
    return event

def stream_dummy_data(interval_seconds=2, output_file=OUTPUT_FILE):
    events = []

    try:
        while True:
            machine = random.choice(MACHINES)
            sensor_payload = generate_sensor_event(machine)
            events.append(sensor_payload)

            print(json.dumps(sensor_payload))
            time.sleep(interval_seconds)

    except KeyboardInterrupt:
        # Use the pathlib object to write the file
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(events, f, indent=2)

        print(
            f"\nStream terminated securely. Saved {len(events)} events to {output_file}",
            file=sys.stderr,
        )

if __name__ == "__main__":
    stream_dummy_data(interval_seconds=1.5)