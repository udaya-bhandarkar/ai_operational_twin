import { useState, useRef, useEffect } from 'react';
import { useChat } from '../hooks/useChat.js';
import ChatMessage from './ChatMessage.jsx';

export default function ChatPanel({ view }) {
  const { messages, send, loading, error } = useChat(view);
  const [draft, setDraft] = useState('');
  const endRef = useRef(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  const submit = () => {
    if (!draft.trim()) return;
    send(draft);
    setDraft('');
  };

  return (
    <div className="chat">
      <div className="chat__header">AI Operational Assistant</div>

      <div className="chat__messages">
        {messages.map((m) => <ChatMessage key={m.id} role={m.role} content={m.content} />)}
        {loading && (
          <div className="bubble bubble--assistant bubble--pending">
            <span className="typing"><span></span><span></span><span></span></span>
          </div>
        )}
        {error && <div className="chat__error">Couldn’t reach the assistant. Try again.</div>}
        <div ref={endRef} />
      </div>

      <div className="chat__input">
        <input
          type="text"
          value={draft}
          placeholder="Ask about waste, costs, machines…"
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') submit(); }}
        />
        <button onClick={submit} disabled={loading || !draft.trim()}>Send</button>
      </div>
      <div className="chat__disclaimer">
        AI can make mistakes. Please verify critical information.
      </div>
    </div>
  );
}