import { useState } from 'react';
import TopBar from './components/TopBar.jsx';
import KpiGrid from './components/KpiGrid.jsx';
import WasteOverTimeChart from './components/WasteOverTimeChart.jsx';
import WasteByMachineChart from './components/WasteByMachineChart.jsx';
import TopEventsTable from './components/TopEventsTable.jsx';
import ChatPanel from './components/ChatPanel.jsx';

export default function App() {
  const [scope, setScope] = useState({ view: 'ceo', facilityId: null, departmentId: null });

  return (
    <div className="app">
      <TopBar scope={scope} onScopeChange={setScope} />

      <div className="app__body">
        <main className="dashboard">
          <KpiGrid scope={scope} />

          <section className="dashboard__charts">
            <WasteOverTimeChart scope={scope} />
            <WasteByMachineChart scope={scope} />
          </section>

          <TopEventsTable scope={scope} />
        </main>

        <aside className="dashboard__chat">
          <ChatPanel view={scope.view} />
        </aside>
      </div>
    </div>
  );
}