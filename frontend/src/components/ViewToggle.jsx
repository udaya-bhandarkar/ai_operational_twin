import { VIEWS } from '../config/constants';

export default function ViewToggle({ value, onChange }) {
  return (
    <div className="view-toggle" role="tablist">
      {VIEWS.map((v) => (
        <button
          key={v.id}
          role="tab"
          aria-selected={value === v.id}
          className={`view-toggle__btn ${value === v.id ? 'is-active' : ''}`}
          onClick={() => onChange(v.id)}
        >
          {v.label}
        </button>
      ))}
    </div>
  );
}