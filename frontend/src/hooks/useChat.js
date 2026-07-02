import { useState, useRef, useCallback } from 'react';
import { sendChatMessage } from '../api/client';

export function useChat(view) {
  const [messages, setMessages] = useState([]);
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState(null);
  const threadId = useRef(crypto.randomUUID());

  const send = useCallback(async (text) => {
    const trimmed = text.trim();
    if (!trimmed || loading) return;

    setMessages((prev) => [...prev, { id: crypto.randomUUID(), role: 'user', content: trimmed }]);
    setLoading(true);
    setError(null);
    try {
      const { reply } = await sendChatMessage({ message: trimmed, threadId: threadId.current, view });
      setMessages((prev) => [...prev, { id: crypto.randomUUID(), role: 'assistant', content: reply }]);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }, [view, loading]);

  return { messages, send, loading, error };
}