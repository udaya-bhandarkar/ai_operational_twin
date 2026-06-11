import json
import sys
import time
import random
from datetime import datetime
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
RAW_DATA_DIR = CURRENT_DIR.parent.parent / "data" / "raw"
RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)

MACHINES = {
    "PET_SHREDDER_01": {"facility": "PUNE_RECYCLING_PLANT", "department": "PRE_PROCESSING", "line": "LINE_A"},
    "EXTRUDER_UNIT_01": {"facility": "PUNE_RECYCLING_PLANT", "department": "EXTRUSION", "line": "LINE_B"},
    "SPINNING_LINE_01": {"facility": "PUNE_RECYCLING_PLANT", "department": "FINISHING", "line": "LINE_C"}
}

OUTPUT_FILE = RAW_DATA_DIR / "sensor_data.json"

def generate_sensor_event(machine_id):
    hierarchy = MACHINES[machine_id]
    
    power_kw = random.uniform(280.0, 310.0)
    water_liters = random.uniform(15.0, 25.0)
    is_choking = random.random() < 0.10
    
    if is_choking:
        power_kw = random.uniform(450.0, 550.0)
        water_liters = random.uniform(40.0, 60.0)
        
    material_in_kg = random.uniform(45.0, 50.0) 
    efficiency = random.uniform(0.60, 0.75) if is_choking else random.uniform(0.95, 0.99)
    material_out_kg = material_in_kg * efficiency
    status = "CRITICAL_POWER_WASTE" if power_kw > 300 else "NORMAL"

    event = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "event_type": "machine_telemetry",
        "facility_id": hierarchy["facility"],
        "department_id": hierarchy["department"],
        "line_id": hierarchy["line"],
        "machine_id": machine_id,
        "metrics": {
            "power_consumption_kw": round(power_kw, 2),
            "water_consumption_liters": round(water_liters, 2), # NEW
            "material_intake_kg": round(material_in_kg, 2),
            "material_output_kg": round(material_out_kg, 2),
            "efficiency_ratio": round(efficiency, 3)
        },
        "status": status
    }
    
    return event

def stream_dummy_data(interval_seconds=2, output_file=OUTPUT_FILE):
    events = []
    machine_keys = list(MACHINES.keys())

    try:
        while True:
            machine = random.choice(machine_keys)
            sensor_payload = generate_sensor_event(machine)
            events.append(sensor_payload)

            print(json.dumps(sensor_payload))
            time.sleep(interval_seconds)

    except KeyboardInterrupt:
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(events, f, indent=2)

        print(
            f"\nStream terminated securely. Saved {len(events)} events to {output_file}",
            file=sys.stderr,
        )

if __name__ == "__main__":
    stream_dummy_data(interval_seconds=1.5)