// Renders either the standardized error or the assistant content + metadata.
export default function ResponsePanel({ result }) {
  if (!result) return null;

  if (!result.ok) {
    const { error, status, requestId } = result;
    return (
      <div className="panel error">
        <h2>Error</h2>
        <div className="error-code">
          {status ? `HTTP ${status}` : ""} · {error.code}
        </div>
        <p>{error.message}</p>
        {requestId && <div className="meta-row"><span>Request ID</span><code>{requestId}</code></div>}
      </div>
    );
  }

  const { data, requestId, latencyMs } = result;
  const usage = data.usage ?? {};
  const meta = [
    ["Model", data.model],
    ["Provider", data.provider],
    ["Provider Model", data.provider_model],
    ["Finish Reason", data.finish_reason],
    ["Input Tokens", usage.input_tokens],
    ["Output Tokens", usage.output_tokens],
    ["Total Tokens", usage.total_tokens],
    ["Request ID", requestId ?? data.id],
    ["Round-trip Latency", latencyMs != null ? `${latencyMs} ms` : null],
  ];

  return (
    <div className="panel">
      <h2>Response</h2>
      <div className="content">{data.content}</div>

      <h2>Metadata</h2>
      <div className="meta">
        {meta
          .filter(([, v]) => v !== null && v !== undefined && v !== "")
          .map(([k, v]) => (
            <div className="meta-row" key={k}>
              <span>{k}</span>
              <code>{String(v)}</code>
            </div>
          ))}
      </div>
    </div>
  );
}
