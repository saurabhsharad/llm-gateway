from reportlab.platypus import Spacer
from engine import (
    build_doc, section_header, para, bullet_list, code_block, data_table,
)

story = []

# --- Overview ---
story += section_header("1. Overview", "What the project is, in one breath.")
story.append(para(
    "The <b>LLM Gateway</b> is a single backend API that sits in front of multiple LLM "
    "providers (Gemini and Groq today, extensible to others). Instead of every application "
    "integrating each provider separately, clients call one endpoint — "
    "<b>POST /v1/chat/completions</b> — and the gateway handles authentication, request "
    "validation, provider selection, calling the provider, normalizing the response, and "
    "logging usage. It ships as a three-service Docker stack (frontend, backend, PostgreSQL)."))
story.append(para(
    "<b>The core idea:</b> one API, many providers, with cross-cutting concerns (auth, "
    "logging, error handling, secrets) centralized in one place rather than duplicated in "
    "every client."))
story.append(Spacer(1, 6))

# --- Architecture ---
story += section_header("2. Architecture", "How a request travels through the system.")
story.append(code_block(
    "Browser\n"
    "  -> React frontend (nginx)        [http://localhost:3000]\n"
    "  -> FastAPI gateway               [http://localhost:8000]\n"
    "        request-id middleware\n"
    "        authentication (gateway API key)\n"
    "        request validation (Pydantic)\n"
    "        model registry  (alias -> provider + real model)\n"
    "        GatewayService  (orchestration, no provider branching)\n"
    "        provider factory -> Gemini / Groq adapter -> provider API\n"
    "        response normalization (one common shape)\n"
    "        usage logging\n"
    "  -> PostgreSQL                    [postgres:5432]"))
story.append(para(
    "The backend stays <b>provider-agnostic</b>: adding a provider means adding an adapter "
    "and a registry entry, with no changes to routes, GatewayService, or schemas."))
story.append(Spacer(1, 6))

# --- Request flow ---
story += section_header("3. Request flow (chat completion)")
story.append(bullet_list([
    "A request-ID middleware assigns one <b>req_...</b> id and returns it as <b>X-Request-ID</b>.",
    "The route authenticates the gateway API key and opens a DB session (FastAPI dependencies).",
    "Pydantic validates the body; malformed requests get a 422 before any logic runs.",
    "GatewayService resolves the public model id via the registry and gets the matching adapter.",
    "The adapter translates to the provider's format, calls it over httpx (with a timeout), and normalizes the reply.",
    "The route logs usage metadata to PostgreSQL and returns the standardized response.",
]))
story.append(Spacer(1, 6))

# --- Features ---
story += section_header("4. What's implemented (V1)")
story.append(bullet_list([
    "Unified chat endpoint across providers, plus <b>/health</b> and <b>/v1/models</b>.",
    "Provider abstraction (ABC + adapter pattern); <b>Gemini</b> and <b>Groq</b> adapters.",
    "Model registry mapping public aliases to provider + real model id (config-driven).",
    "API-key authentication; keys stored only as <b>SHA-256 hashes</b> in PostgreSQL.",
    "Usage logging of per-request metadata (never prompts or responses).",
    "Request IDs correlated across response header, logs, and the database.",
    "Standardized error envelope with safe messages; configurable upstream timeouts.",
    "React console UI and a one-command Docker Compose stack.",
]))
story.append(Spacer(1, 6))

# --- Tech stack ---
story += section_header("5. Technology stack")
story.append(data_table(
    ["Layer", "Technology"],
    [["Backend", "Python 3.12, FastAPI, Uvicorn, Pydantic / Pydantic Settings"],
     ["LLM calls", "httpx (async) to Gemini & Groq REST APIs"],
     ["Database", "PostgreSQL 16, SQLAlchemy 2.0, Alembic, psycopg v3"],
     ["Frontend", "React + Vite, served by nginx"],
     ["Infra", "Docker Compose (frontend, backend, postgres)"],
     ["Testing", "pytest (74 tests)"]]))
story.append(Spacer(1, 6))

# --- Data model ---
story += section_header("6. Data model (PostgreSQL)")
story.append(data_table(
    ["Table", "Key columns", "Purpose"],
    [["users", "id, name, created_at", "The client/account behind a key"],
     ["api_keys", "id, user_id, key_hash, is_active, created_at", "Gateway keys (hashed)"],
     ["requests", "request_id, user_id, api_key_id, model, provider, tokens, latency_ms, status, error_code", "Usage metadata log"]]))
story.append(para(
    "<b>Privacy by default:</b> only metadata is stored — there is no column for prompt or "
    "response content."))
story.append(Spacer(1, 6))

# --- Security ---
story += section_header("7. Security model — two kinds of API keys")
story.append(data_table(
    ["", "Gateway API key", "Provider API key"],
    [["Used by", "client -> this gateway", "the gateway -> the LLM provider"],
     ["Sent as", "Authorization: Bearer gw_...", "provider-specific header (backend only)"],
     ["Stored as", "SHA-256 hash in PostgreSQL", "backend .env only; never in the frontend"]]))
story.append(para(
    "Raw keys are never stored or logged; provider failures are translated into safe errors "
    "so provider internals never reach the client."))
story.append(Spacer(1, 6))

# --- Reliability ---
story += section_header("8. Reliability & error handling")
story.append(bullet_list([
    "Centralized exception handlers produce one JSON shape: <b>{\"error\":{\"code\",\"message\"}}</b>.",
    "Status/code mapping: 401 UNAUTHORIZED, 404 UNKNOWN_MODEL, 422 VALIDATION_ERROR, "
    "502 PROVIDER_ERROR, 503 PROVIDER_UNAVAILABLE, 500 INTERNAL_ERROR.",
    "Upstream calls are bounded by <b>LLM_TIMEOUT_SECONDS</b> (default 30); a timeout returns a clean 502.",
    "Usage logging is failure-safe — a DB logging error never changes the client's result.",
    "No automatic retries or provider fallback in V1 (deliberate scope choice).",
]))
story.append(Spacer(1, 6))

# --- Running it ---
story += section_header("9. Running it")
story.append(code_block(
    "# 1. Put provider keys + GATEWAY_API_KEYS in backend/.env (from .env.example)\n"
    "# 2. Start the whole stack:\n"
    "docker compose up --build\n\n"
    "# 3. Seed a gateway API key (once):\n"
    "docker compose exec backend python -m app.db.seed\n\n"
    "# 4. Run the test suite inside the container:\n"
    "docker compose exec backend pytest -q\n\n"
    "# Frontend: http://localhost:3000   Backend/docs: http://localhost:8000/docs"))
story.append(para(
    "The backend runs <b>alembic upgrade head</b> before serving; a failed migration stops "
    "the container instead of serving a broken schema."))
story.append(Spacer(1, 6))

# --- Scope ---
story += section_header("10. Scope & limitations (honest)")
story.append(bullet_list([
    "Gemini and Groq adapters are implemented; OpenAI/Anthropic exist as registry aliases "
    "only and return 503 until an adapter is added.",
    "Client chooses the model — there is no intelligent/automatic routing.",
    "No retries, fallback, streaming, rate limiting, RBAC, or caching (all deferred to V2).",
    "Authentication only (identity); authorization/quotas are future work.",
    "These are intentional V1 boundaries, enabled-for-later by the clean architecture.",
]))

build_doc("00_Project_Overview.pdf",
          "LLM Gateway V1 — Project Overview",
          "One-page-at-a-glance summary · unified multi-provider gateway (FastAPI + PostgreSQL + React + Docker)",
          story)
