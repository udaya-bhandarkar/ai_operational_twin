import { useState, useRef, useEffect } from 'react';
import { VIEWS } from '../config/constants';
import { useScopeOptions } from '../hooks/useScopeOptions.js';


export default function ViewToggle({ scope, onChange }) {
  const { facilities, departments } = useScopeOptions();
  const [openMenu, setOpenMenu] = useState(null);        // 'factory' | 'department' | null
  const [pendingFacility, setPendingFacility] = useState(null); // for the 2-step dept flow
  const ref = useRef(null);

  // Close the dropdown when clicking outside it
  useEffect(() => {
    function handleClickOutside(e) {
      if (ref.current && !ref.current.contains(e.target)) {
        setOpenMenu(null);
        setPendingFacility(null);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // CEO: no dropdown, just select
  function selectCeo() {
    onChange({ view: 'ceo', facilityId: null, departmentId: null });
    setOpenMenu(null);
  }

  // Factory Manager: pick a facility
  function selectFacility(facilityId) {
    onChange({ view: 'factory', facilityId, departmentId: null });
    setOpenMenu(null);
  }

  // Department Manager: step 1 pick facility, step 2 pick department
  function selectDepartment(facilityId, departmentId) {
    onChange({ view: 'department', facilityId, departmentId });
    setOpenMenu(null);
    setPendingFacility(null);
  }

  function toggleMenu(menu) {
    setOpenMenu((cur) => (cur === menu ? null : menu));
    setPendingFacility(null);
  }

  // departments belonging to the facility picked in step 1
  const deptsForPending = departments.filter((d) => d.facility_id === pendingFacility);

  return (
    <div className="view-toggle" role="tablist" ref={ref}>
      {/* CEO */}
      <button
        role="tab"
        aria-selected={scope.view === 'ceo'}
        className={`view-toggle__btn ${scope.view === 'ceo' ? 'is-active' : ''}`}
        onClick={selectCeo}
      >
        CEO
      </button>

      {/* Factory Manager */}
      <div className="view-toggle__group">
        <button
          role="tab"
          aria-selected={scope.view === 'factory'}
          className={`view-toggle__btn ${scope.view === 'factory' ? 'is-active' : ''}`}
          onClick={() => toggleMenu('factory')}
        >
          Factory Manager <span className="caret">▾</span>
        </button>
        {openMenu === 'factory' && (
          <div className="dropdown">
            {facilities.map((f) => (
              <button key={f.facility_id} className="dropdown__item"
                onClick={() => selectFacility(f.facility_id)}>
                {f.label}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Department Manager (two-step) */}
      <div className="view-toggle__group">
        <button
          role="tab"
          aria-selected={scope.view === 'department'}
          className={`view-toggle__btn ${scope.view === 'department' ? 'is-active' : ''}`}
          onClick={() => toggleMenu('department')}
        >
          Department Manager <span className="caret">▾</span>
        </button>
        {openMenu === 'department' && (
          <div className="dropdown">
            {!pendingFacility ? (
              <>
                <div className="dropdown__label">Select facility</div>
                {facilities.map((f) => (
                  <button key={f.facility_id} className="dropdown__item"
                    onClick={() => setPendingFacility(f.facility_id)}>
                    {f.label} ›
                  </button>
                ))}
              </>
            ) : (
              <>
                <div className="dropdown__label">
                  <button className="dropdown__back" onClick={() => setPendingFacility(null)}>‹ Back</button>
                </div>
                {deptsForPending.map((d) => (
                  <button key={d.department_id} className="dropdown__item"
                    onClick={() => selectDepartment(pendingFacility, d.department_id)}>
                    {d.label}
                  </button>
                ))}
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}