import { useState, useRef, useEffect } from 'react';
import TopBar from './components/TopBar.jsx';
import KpiGrid from './components/KpiGrid.jsx';
import WasteOverTimeChart from './components/WasteOverTimeChart.jsx';
import WasteByMachineChart from './components/WasteByMachineChart.jsx';
import TopEventsTable from './components/TopEventsTable.jsx';
import ChatPanel from './components/ChatPanel.jsx';

export default function App() {
  const [scope, setScope] = useState({ view: 'ceo', facilityId: null, departmentId: null });
  const contentRef = useRef(null);
  const [dashboardHeight, setDashboardHeight] = useState(null);
  const [isStacked, setIsStacked] = useState(window.innerWidth <= 1100);
  const [needsBottomPadding, setNeedsBottomPadding] = useState(false);

  // Track narrow-screen stacked layout
  useEffect(() => {
    const mq = window.matchMedia('(max-width: 1100px)');
    const handleChange = (e) => setIsStacked(e.matches);
    mq.addEventListener('change', handleChange);
    return () => mq.removeEventListener('change', handleChange);
  }, []);

  // Measure dashboard content height (for chat panel height-matching + short-window padding)
  useEffect(() => {
    const el = contentRef.current;
    if (!el) return;

    const checkFit = () => {
      const contentHeight = el.scrollHeight;
      setDashboardHeight(contentHeight);

      const dashboardEl = el.parentElement;
      const topOffset = dashboardEl.getBoundingClientRect().top + window.scrollY;
      const totalNeededHeight = topOffset + contentHeight;
      setNeedsBottomPadding(totalNeededHeight > window.innerHeight);
    };

    checkFit();
    window.addEventListener('resize', checkFit);

    const observer = new ResizeObserver(checkFit);
    observer.observe(el);

    return () => {
      window.removeEventListener('resize', checkFit);
      observer.disconnect();
    };
  }, []);

  return (
    <div className={`app ${needsBottomPadding ? 'app--needs-padding' : ''}`}>
      <TopBar scope={scope} onScopeChange={setScope} />

      <div className="app__body">
        <main className="dashboard">
          <div ref={contentRef} className="dashboard__content">
            <KpiGrid scope={scope} />

            <section className="dashboard__charts">
              <WasteOverTimeChart scope={scope} />
              <WasteByMachineChart scope={scope} />
            </section>

            <TopEventsTable scope={scope} />
          </div>
        </main>

        <aside 
          className="dashboard__chat"
          style={!isStacked && dashboardHeight ? { height: dashboardHeight, alignSelf: 'start' } : undefined}
        >

          <ChatPanel view={scope.view} />
        </aside>
      </div>
    </div>
  );
}