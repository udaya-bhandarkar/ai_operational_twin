export default function ErrorState({ message, onRetry }) {
  return (
    <div className="state state--error">
      <span>{message ?? 'Something went wrong.'}</span>
      {onRetry && <button onClick={onRetry}>Retry</button>}
    </div>
  );
}