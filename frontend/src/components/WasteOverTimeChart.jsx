import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid } from 'recharts';
import { useWasteOverTime } from '../hooks/useWasteOverTime.js';
import Card from './ui/Card.jsx';
import { formatINR, formatTime } from '../utils/format.js';
import { COLORS } from '../config/constants';

export default function WasteOverTimeChart({ view }) {
  const { data, loading, error } = useWasteOverTime(view);
  const points = data?.points ?? [];

  return (
    <Card title="Waste Cost Over Time" loading={loading} error={error} empty={!points.length}>
      <ResponsiveContainer width="100%" height={240}>
        <BarChart data={points} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="bucket" tickFormatter={formatTime} fontSize={11} />
          <YAxis tickFormatter={(v) => `₹${v}`} fontSize={11} width={56} />
          <Tooltip formatter={(v) => formatINR(v)} labelFormatter={formatTime} />
          <Bar dataKey="waste_cost_inr" name="Waste cost" fill={COLORS.accent} radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </Card>
  );
}