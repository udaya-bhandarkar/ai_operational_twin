import { useMemo } from 'react';
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip } from 'recharts';
import { useWasteByMachine } from '../hooks/useWasteByMachine.js';
import Card from './ui/Card.jsx';
import { formatINR } from '../utils/format.js';
import { COLORS } from '../config/constants';

// Measures rendered text width using canvas, matching the axis font size
function getTextWidth(text, font = '11px sans-serif') {
  const canvas = getTextWidth.canvas || (getTextWidth.canvas = document.createElement('canvas'));
  const context = canvas.getContext('2d');
  context.font = font;
  return context.measureText(text).width;
}

export default function WasteByMachineChart({ scope }) {
  const { data, loading, error } = useWasteByMachine(scope);
  const machines = data?.machines ?? [];

  const yAxisWidth = useMemo(() => {
    if (!machines.length) return 130;
    const longest = machines.reduce((max, m) => {
      const width = getTextWidth(m.machine_id);
      return width > max ? width : max;
    }, 0);
    return Math.min(Math.ceil(longest), 220); // capped at 220px
  }, [machines]);

  return (
    <Card title="Waste Cost by Machine" loading={loading} error={error} empty={!machines.length}>
      <ResponsiveContainer width="100%" height={240}>
        <BarChart data={machines} layout="vertical" margin={{ top: 8, right: 16, left: 8, bottom: 0 }}>
          <XAxis type="number" tickFormatter={(v) => `₹${v}`} fontSize={11} />
          <YAxis type="category" dataKey="machine_id" width={yAxisWidth} fontSize={11} />
          <Tooltip formatter={(v) => formatINR(v)} />
          <Bar dataKey="waste_cost_inr" name="Waste cost" fill={COLORS.primary} radius={[0, 4, 4, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </Card>
  );
}