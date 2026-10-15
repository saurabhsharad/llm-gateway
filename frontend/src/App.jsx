import { useEffect, useState } from "react";
import ModelSelector from "./components/ModelSelector.jsx";
import ChatInput from "./components/ChatInput.jsx";
import ResponsePanel from "./components/ResponsePanel.jsx";
import { fetchModels, sendChat } from "./services/api.js";

export default function App() {
  const [apiKey, setApiKey] = useState("");
  const [models, setModels] = useState([]);
  const [model, setModel] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [modelsError, setModelsError] = useState(null);

  // On load, populate the model dropdown from the actual backend (GET /v1/models).
  useEffect(() => {
    fetchModels()
      .then((list) => {
        setModels(list);
        if (list.length > 0) setModel(list[0].id);
      })
      .catch((err) => setModelsError(err.message));
  }, []);

  const canSend = apiKey.trim() !== "" && model !== "" && message.trim() !== "";

  async function handleSend() {
    setLoading(true);
    setResult(null);
    const res = await sendChat({ apiKey: apiKey.trim(), model, content: message });
    setResult(res);
    setLoading(false);
  }

  return (
    <div className="app">
      <header>
        <h1>LLM Gateway</h1>
        <p className="subtitle">Developer console — one API for Gemini &amp; Groq</p>
      </header>

      <label className="field">
        <span className="label">Gateway API Key</span>
        <input
          type="password"
          placeholder="gw_…"
          value={apiKey}
          onChange={(e) => setApiKey(e.target.value)}
          autoComplete="off"
        />
        <small className="hint">
          Your client key for this gateway (sent as <code>Authorization: Bearer</code>).
          Not a provider key.
        </small>
      </label>

      <ModelSelector models={models} value={model} onChange={setModel} disabled={loading} />
      {modelsError && <div className="inline-error">Could not load models: {modelsError}</div>}

      <ChatInput
        value={message}
        onChange={setMessage}
        onSend={handleSend}
        loading={loading}
        canSend={canSend}
      />

      <ResponsePanel result={result} />
    </div>
  );
}
