// Message textarea + Send button. Send is disabled while a request is running.
export default function ChatInput({ value, onChange, onSend, loading, canSend }) {
  return (
    <div className="field">
      <span className="label">Message</span>
      <textarea
        rows={5}
        placeholder="Explain polymorphism in two sentences…"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={loading}
      />
      <button className="send" onClick={onSend} disabled={loading || !canSend}>
        {loading ? "Generating…" : "Send"}
      </button>
    </div>
  );
}
