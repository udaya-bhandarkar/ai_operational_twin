const inr = new Intl.NumberFormat('en-IN', {
  style: 'currency', currency: 'INR', maximumFractionDigits: 2,
});

export const formatINR = (v) => (v == null ? '—' : inr.format(v));

export const formatPercent = (ratio) =>
  ratio == null ? '—' : `${(ratio * 100).toFixed(1)}%`;

export const formatNumber = (v, decimals = 0) =>
  v == null ? '—' : Number(v).toLocaleString('en-IN', { maximumFractionDigits: decimals });

export const formatTime = (ts) =>
  ts ? new Date(ts).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' }) : '—';

export const formatDateTime = (ts) =>
  ts ? new Date(ts).toLocaleString('en-IN') : '—';

export const formatCO2 = (v) =>
  v == null ? '—' : `${Number(v).toLocaleString('en-IN', { maximumFractionDigits: 0 })} kg`;

export const formatDelta = (fraction) => {
  if (fraction == null) return null;
  const pct = (fraction * 100).toFixed(1);
  const direction = fraction > 0 ? 'up' : fraction < 0 ? 'down' : 'flat';
  const sign = fraction > 0 ? '+' : '';
  return { text: `${sign}${pct}% since yesterday`, direction };
};