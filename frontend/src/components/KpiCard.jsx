import { formatDelta } from '../utils/format.js';

export default function KpiCard({ label, value, delta, accent, loading, error }) {
  const d = formatDelta(delta);
  return (
    <div className="kpi-card" style={{ borderTopColor: accent }}>
      <div className="kpi-card__label">{label}</div>
      <div className="kpi-card__value">
        {error ? '—' : loading ? '…' : value}
      </div>
      {d && (
        <div className={`kpi-card__delta kpi-card__delta--${d.direction}`}>
          {d.direction === 'up' ? '▲' : d.direction === 'down' ? '▼' : '–'} {d.text}
        </div>
      )}
    </div>
  );
}