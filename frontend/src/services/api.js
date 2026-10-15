// API service: the single place the frontend talks to the FastAPI gateway.
// The frontend NEVER calls Gemini/Groq directly and never holds provider keys.
// The only credential it handles is the CLIENT's Gateway API key, sent as a
// Bearer token to OUR gateway.

const BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

const REQUEST_ID_HEADER = "X-Request-ID";

/** Fetch the list of public models the gateway serves (GET /v1/models). */
export async function fetchModels() {
  const res = await fetch(`${BASE_URL}/v1/models`);
  if (!res.ok) throw new Error(`Failed to load models (HTTP ${res.status})`);
  const data = await res.json();
  return data.models ?? [];
}

/**
 * Send a chat completion (POST /v1/chat/completions).
 * Returns a normalized result: { ok, status, requestId, latencyMs, data, error }.
 * `data` is the ChatCompletionResponse on success; `error` is {code,message} on failure.
 */
export async function sendChat({ apiKey, model, content }) {
  const started = performance.now();
  let res;
  try {
    res = await fetch(`${BASE_URL}/v1/chat/completions`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        // Client -> Gateway authentication. NOT a provider key.
        Authorization: `Bearer ${apiKey}`,
      },
      body: JSON.stringify({
        model,
        messages: [{ role: "user", content }],
      }),
    });
  } catch (networkErr) {
    // Gateway unreachable (server down / CORS / network).
    return {
      ok: false,
      status: 0,
      requestId: null,
      latencyMs: Math.round(performance.now() - started),
      error: { code: "NETWORK_ERROR", message: "Could not reach the gateway." },
    };
  }

  const latencyMs = Math.round(performance.now() - started);
  const requestId = res.headers.get(REQUEST_ID_HEADER);

  let body = null;
  try {
    body = await res.json();
  } catch {
    body = null;
  }

  if (res.ok) {
    return { ok: true, status: res.status, requestId: requestId ?? body?.id, latencyMs, data: body };
  }

  // Standardized gateway error envelope: { "error": { "code", "message" } }.
  const error = body?.error ?? {
    code: `HTTP_${res.status}`,
    message: "The request failed.",
  };
  return { ok: false, status: res.status, requestId, latencyMs, error };
}
