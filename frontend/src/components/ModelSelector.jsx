// Dropdown of public model aliases, populated from GET /v1/models (never hardcoded).
export default function ModelSelector({ models, value, onChange, disabled }) {
  return (
    <label className="field">
      <span className="label">Model</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled || models.length === 0}
      >
        {models.length === 0 && <option value="">Loading models…</option>}
        {models.map((m) => (
          <option key={m.id} value={m.id}>
            {m.id} ({m.provider})
          </option>
        ))}
      </select>
    </label>
  );
}
