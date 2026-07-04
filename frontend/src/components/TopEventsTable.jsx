import { useTopEvents } from '../hooks/useTopEvents.js';
import Card from './ui/Card.jsx';
import { formatINR, formatPercent, formatTime } from '../utils/format.js';

export default function TopEventsTable({ scope }) {
  const { data, loading, error } = useTopEvents(scope);
  const events = data?.events ?? [];

  return (
    <Card title="⚠ Top 5 Waste Events" loading={loading} error={error} empty={!events.length}>
      <table className="events-table">
        <thead>
          <tr>
            <th>#</th><th>Machine</th><th>Time</th><th>Efficiency</th>
            <th>Energy Cost</th><th>Total Waste</th><th>Status</th>
          </tr>
        </thead>
        <tbody>
          {events.map((e, i) => (
            <tr key={`${e.machine_id}-${e.timestamp}`}>
              <td>{i + 1}</td>
              <td>{e.machine_id}</td>
              <td>{formatTime(e.timestamp)}</td>
              <td>{formatPercent(e.efficiency_ratio)}</td>
              <td>{formatINR(e.energy_cost_inr)}</td>
              <td className="events-table__waste">{formatINR(e.total_waste_inr)}</td>
              <td><span className={`badge badge--${e.status?.toLowerCase()}`}>{e.status}</span></td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}