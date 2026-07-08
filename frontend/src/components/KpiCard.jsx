export default function KpiCard({ label, value, accent, loading, error }) {
  return (
    <div className="kpi-card" style={{ borderTopColor: accent }}>
      <div className="kpi-card__label">{label}</div>
      <div className="kpi-card__value">
        {error ? '—' : loading ? '…' : value}
      </div>
    </div>
  );
}