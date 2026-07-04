const kpis = {
  total_waste_cost_inr: 18450.5,
  energy_waste_cost_inr: 12300,
  material_waste_cost_inr: 6150.5,
  water_waste_cost_inr: 2840.0,
  efficiency_ratio: 0.786,
  carbon_emissions_kg_co2: 14820.0,
  deltas: { total_waste_cost_inr: 0.042, energy_waste_cost_inr: -0.015, material_waste_cost_inr: 0.11, 
            water_waste_cost_inr: 0.03, efficiency_ratio: -0.003, carbon_emissions_kg_co2: 0.018 },
  as_of: new Date().toISOString(),
};
const wasteOverTime = {
  range: '24h',
  points: Array.from({ length: 12 }, (_, i) => ({
    bucket: new Date(Date.now() - (11 - i) * 3.6e6).toISOString(),
    waste_cost_inr: 400 + Math.round(Math.random() * 1200),
  })),
};
const wasteByMachine = {
  machines: [
    { machine_id: 'PET_SHREDDER_01',  waste_cost_inr: 9100 },
    { machine_id: 'EXTRUDER_UNIT_01', waste_cost_inr: 5400 },
    { machine_id: 'SPINNING_LINE_01', waste_cost_inr: 3950.5 },
  ],
};
const topEvents = {
  events: wasteByMachine.machines.map((m, i) => ({
    machine_id: m.machine_id,
    timestamp: new Date(Date.now() - i * 6e5).toISOString(),
    efficiency_ratio: 0.7 + i * 0.03,
    energy_cost_inr: 10 + i,
    total_waste_inr: m.waste_cost_inr,
    status: i === 0 ? 'CRITICAL_POWER_WASTE' : 'NORMAL',
  })),
};
const machines = {
  machines: wasteByMachine.machines.map((m, i) => ({
    machine_id: m.machine_id, status: i === 0 ? 'CRITICAL_POWER_WASTE' : 'NORMAL',
  })),
};
const facilities = {
  facilities: [
    { facility_id: 'CHENNAI_RECYCLING_PLANT', label: 'Chennai Recycling Plant' },
    { facility_id: 'PUNE_RECYCLING_PLANT',    label: 'Pune Recycling Plant' },
  ],
};
const departments = {
  departments: [
    { department_id: 'PRE_PROCESSING', label: 'Pre-Processing', facility_id: 'CHENNAI_RECYCLING_PLANT' },
    { department_id: 'WASHING',        label: 'Washing',        facility_id: 'CHENNAI_RECYCLING_PLANT' },
    { department_id: 'EXTRUSION',      label: 'Extrusion',      facility_id: 'CHENNAI_RECYCLING_PLANT' },
    { department_id: 'PRE_PROCESSING', label: 'Pre-Processing', facility_id: 'PUNE_RECYCLING_PLANT' },
    { department_id: 'WASHING',        label: 'Washing',        facility_id: 'PUNE_RECYCLING_PLANT' },
    { department_id: 'FINISHING',      label: 'Finishing',      facility_id: 'PUNE_RECYCLING_PLANT' },
  ],
};

export function respond(path, options) {
  if (path.startsWith('/kpis'))             return Promise.resolve(kpis);
  if (path.startsWith('/waste-over-time'))  return Promise.resolve(wasteOverTime);
  if (path.startsWith('/waste-by-machine')) return Promise.resolve(wasteByMachine);
  if (path.startsWith('/top-events'))       return Promise.resolve(topEvents);
  if (path.startsWith('/machines'))         return Promise.resolve(machines);
  if (path.startsWith('/facilities'))   return Promise.resolve(facilities);
  if (path.startsWith('/departments'))  return Promise.resolve(departments);
  if (path.startsWith('/chat')) {
    const { message } = JSON.parse(options.body);
    return new Promise((r) => setTimeout(() =>
      r({ reply: `(mock) You asked: "${message}". PET_SHREDDER_01 leads waste today.` }), 600));
  }
  return Promise.reject(new Error(`No mock for ${path}`));
}