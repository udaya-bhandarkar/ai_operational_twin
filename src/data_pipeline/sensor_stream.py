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
    # FACILITY 1: PUNE RECYCLING PLANT
    # Department: PRE_PROCESSING
    "PUNE_BALE_BREAKER_01": {"facility": "PUNE_RECYCLING_PLANT", "department": "PRE_PROCESSING", "line": "LINE_A"},
    "PUNE_PET_SHREDDER_01": {"facility": "PUNE_RECYCLING_PLANT", "department": "PRE_PROCESSING", "line": "LINE_A"},
    "PUNE_PET_SHREDDER_02": {"facility": "PUNE_RECYCLING_PLANT", "department": "PRE_PROCESSING", "line": "LINE_A"},

    # Department: WASHING
    "PUNE_HOT_WASHER_01": {"facility": "PUNE_RECYCLING_PLANT", "department": "WASHING", "line": "LINE_A"},
    "PUNE_SINK_FLOAT_01": {"facility": "PUNE_RECYCLING_PLANT", "department": "WASHING", "line": "LINE_A"},

    # Department: EXTRUSION
    "PUNE_EXTRUDER_01": {"facility": "PUNE_RECYCLING_PLANT", "department": "EXTRUSION", "line": "LINE_B"},
    "PUNE_PELLETIZER_01": {"facility": "PUNE_RECYCLING_PLANT", "department": "EXTRUSION", "line": "LINE_B"},

    # Department: FINISHING
    "PUNE_SPINNING_LINE_01": {"facility": "PUNE_RECYCLING_PLANT", "department": "FINISHING", "line": "LINE_C"},
    "PUNE_WINDING_UNIT_01": {"facility": "PUNE_RECYCLING_PLANT", "department": "FINISHING", "line": "LINE_C"},

    # FACILITY 2: CHENNAI RECYCLING PLANT
    # Department: PRE_PROCESSING
    "CHENNAI_BALE_BREAKER_01": {"facility": "CHENNAI_RECYCLING_PLANT", "department": "PRE_PROCESSING", "line": "LINE_A"},
    "CHENNAI_OPTICAL_SORTER_01": {"facility": "CHENNAI_RECYCLING_PLANT", "department": "PRE_PROCESSING", "line": "LINE_A"},
    "CHENNAI_PET_SHREDDER_01": {"facility": "CHENNAI_RECYCLING_PLANT", "department": "PRE_PROCESSING", "line": "LINE_A"},

    # Department: WASHING
    "CHENNAI_COLD_WASHER_01": {"facility": "CHENNAI_RECYCLING_PLANT", "department": "WASHING", "line": "LINE_B"},
    "CHENNAI_SINK_FLOAT_01": {"facility": "CHENNAI_RECYCLING_PLANT", "department": "WASHING", "line": "LINE_B"},

    # Department: EXTRUSION
    "CHENNAI_EXTRUDER_01": {"facility": "CHENNAI_RECYCLING_PLANT", "department": "EXTRUSION", "line": "LINE_C"},
    "CHENNAI_EXTRUDER_02": {"facility": "CHENNAI_RECYCLING_PLANT", "department": "EXTRUSION", "line": "LINE_C"},
    
    # Department: FINISHING
    "CHENNAI_SPINNING_LINE_01": {"facility": "CHENNAI_RECYCLING_PLANT", "department": "FINISHING", "line": "LINE_D"}
}

# Dynamic timestamped file name for partitioning
session_time = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
OUTPUT_FILE = RAW_DATA_DIR / f"sensor_data_{session_time}.json"

def generate_sensor_event(machine_id):
    hierarchy = MACHINES[machine_id]
    
    power_kw = random.uniform(280.0, 300.0)
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
            "water_consumption_liters": round(water_liters, 2), 
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
        # Writes strictly to the uniquely named file for this session
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(events, f, indent=2)

        print(
            f"\nStream terminated securely. Saved {len(events)} events to {output_file.name}",
            file=sys.stderr,
        )

if __name__ == "__main__":
    stream_dummy_data(interval_seconds=1.5)