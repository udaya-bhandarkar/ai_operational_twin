import { useKpis } from '../hooks/useKpis.js';
import KpiCard from './KpiCard.jsx';
import { formatINR, formatPercent, formatCO2 } from '../utils/format.js';
import { COLORS } from '../config/constants';

export default function KpiGrid({ scope }) {
  const { data, loading, error } = useKpis(scope);

  const cards = [
    { key: 'total_waste_cost_inr',    label: 'Total Waste Cost (Today)', format: formatINR,     accent: COLORS.deep },
    { key: 'energy_waste_cost_inr',   label: 'Energy Waste Cost',        format: formatINR,     accent: COLORS.accent },
    { key: 'material_waste_cost_inr', label: 'Material Waste Cost',      format: formatINR,     accent: COLORS.primary },
    { key: 'efficiency_ratio',        label: 'Efficiency Ratio',         format: formatPercent, accent: COLORS.primary },
    { key: 'carbon_emissions_kg_co2',  label: 'Carbon Emissions',        format: formatCO2,     accent: COLORS.deep },
    { key: 'water_waste_cost_inr',     label: 'Water Cost',              format: formatINR,     accent: COLORS.accent },
  ];

  return (
    <section className="kpi-grid">
      {cards.map((c) => (
        <KpiCard
          key={c.key}
          label={c.label}
          value={c.format(data?.[c.key])}
          accent={c.accent}
          loading={loading}
          error={error}
        />
      ))}
    </section>
  );
}