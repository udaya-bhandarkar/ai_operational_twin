import { useState } from 'react';
import TopBar from './components/TopBar.jsx';
import KpiGrid from './components/KpiGrid.jsx';
import WasteOverTimeChart from './components/WasteOverTimeChart.jsx';
import WasteByMachineChart from './components/WasteByMachineChart.jsx';
import TopEventsTable from './components/TopEventsTable.jsx';
import ChatPanel from './components/ChatPanel.jsx';

export default function App() {
  const [view, setView] = useState('ceo');

  return (
    <div className="app">
      <TopBar view={view} onViewChange={setView} />

      <div className="app__body">
        <main className="dashboard">
          <KpiGrid view={view} />

          <section className="dashboard__charts">
            <WasteOverTimeChart view={view} />
            <WasteByMachineChart view={view} />
          </section>

          <TopEventsTable />
        </main>

        <aside className="dashboard__chat">
          <ChatPanel view={view} />
        </aside>
      </div>
    </div>
  );
}