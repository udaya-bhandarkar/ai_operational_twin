import { useKpis } from '../hooks/useKpis.js';
import KpiCard from './KpiCard.jsx';
import { formatINR, formatPercent } from '../utils/format.js';
import { COLORS } from '../config/constants';

export default function KpiGrid({ view }) {
  const { data, loading, error } = useKpis(view);
  const d = data?.deltas ?? {};

  const cards = [
    { key: 'total_waste_cost_inr',    label: 'Total Waste Cost (Today)', format: formatINR,     accent: COLORS.deep },
    { key: 'energy_waste_cost_inr',   label: 'Energy Waste Cost',        format: formatINR,     accent: COLORS.accent },
    { key: 'material_waste_cost_inr', label: 'Material Waste Cost',      format: formatINR,     accent: COLORS.primary },
    { key: 'efficiency_ratio',        label: 'Efficiency Ratio',         format: formatPercent, accent: COLORS.primary },
  ];

  return (
    <section className="kpi-grid">
      {cards.map((c) => (
        <KpiCard
          key={c.key}
          label={c.label}
          value={c.format(data?.[c.key])}
          delta={d[c.key]}
          accent={c.accent}
          loading={loading}
          error={error}
        />
      ))}
    </section>
  );
}