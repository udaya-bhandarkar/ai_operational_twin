import LoadingState from './LoadingState.jsx';
import ErrorState from './ErrorState.jsx';

export default function Card({ title, loading, error, empty, children }) {
  return (
    <div className="card">
      {title && <div className="card__title">{title}</div>}
      <div className="card__body">
        {error ? <ErrorState message={error.message} />
          : loading ? <LoadingState />
          : empty ? <div className="card__empty">No data yet.</div>
          : children}
      </div>
    </div>
  );
}