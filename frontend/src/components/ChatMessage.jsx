import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

export default function ChatMessage({ role, content, pending }) {
  const isAssistant = role === 'assistant';
  return (
    <div className={`bubble bubble--${role} ${pending ? 'bubble--pending' : ''}`}>
      {isAssistant ? (
        // Assistant replies are markdown (bold, tables, lists). User text stays literal.
        <div className="markdown">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
        </div>
      ) : (
        content
      )}
    </div>
  );
}
