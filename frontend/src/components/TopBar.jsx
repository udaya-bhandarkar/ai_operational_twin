import ViewToggle from './ViewToggle.jsx';
import { formatTime } from '../utils/format.js';

export default function TopBar({ view, onViewChange }) {
  return (
    <header className="topbar">
      <div className="topbar__title">
        <h1>AI Operational Twin</h1>
        <span className="topbar__subtitle">Ekak Innovations</span>
      </div>
      <div className="topbar__updated">Last updated {formatTime(new Date().toISOString())}</div>
      <ViewToggle value={view} onChange={onViewChange} />
    </header>
  );
}