export default function ChatMessage({ role, content, pending }) {
  return (
    <div className={`bubble bubble--${role} ${pending ? 'bubble--pending' : ''}`}>
      {content}
    </div>
  );
}