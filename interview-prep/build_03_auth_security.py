from engine import build_pdf

sections = [
    {
        "name": "1. Two Kinds of API Keys",
        "intro": "The single most important security distinction in the project.",
        "questions": [
            {
                "q": "Q1. Explain the difference between the gateway API key and the provider API keys.",
                "level": "EASY",
                "answer": "The gateway API key authenticates a CLIENT to OUR gateway and is sent as "
                          "Authorization: Bearer gw_... . The provider API keys (Gemini, Groq) authenticate "
                          "the GATEWAY to the external providers and live only in the backend. They are "
                          "completely separate credentials and must never be mixed.",
                "simple": "Client key = 'who may call us'. Provider key = 'how we call the LLM'.",
                "example": "The React frontend only ever handles the gateway key (typed by the user). Provider "
                           "keys stay in backend/.env and never reach the browser bundle.",
                "code": "Client  --(Bearer gw_...)-->  Gateway  --(provider key)-->  Gemini/Groq",
                "tip": "This is almost always asked. Say it crisply and give the 'never in the frontend' line.",
            },
            {
                "q": "Q2. How do you make sure provider keys never leak to the frontend?",
                "level": "MEDIUM",
                "answer": "Provider keys are read only by backend config and used only inside adapters, sent in "
                          "request headers (never logged, never in URLs). The frontend bundle is built with "
                          "only VITE_API_BASE_URL (a non-secret). We scanned the built bundle and image to "
                          "confirm no provider keys or the gateway key appear.",
                "simple": "Keys stay server-side; the browser gets code, not secrets.",
                "example": "VITE_* values are embedded in the browser bundle, so by rule only the non-secret "
                           "base URL goes there; everything sensitive is backend-only.",
                "followups": ["Why can't VITE_* hold secrets? (anything in the frontend build ships to every browser)"],
            },
        ],
    },
    {
        "name": "2. How Authentication Works",
        "intro": "Validating a client key on every protected request.",
        "questions": [
            {
                "q": "Q3. Walk through what happens when a request with a gateway key arrives.",
                "level": "MEDIUM",
                "answer": "A FastAPI dependency, require_api_key, extracts the Bearer token using "
                          "HTTPBearer(auto_error=False). It hashes the token with SHA-256 and looks up an "
                          "active api_keys row by that hash. If found, it resolves the owning user into a "
                          "ClientIdentity; if missing/inactive, it raises AuthenticationError -> 401.",
                "simple": "Hash the presented key, look it up, allow if it matches an active key.",
                "code": "require_api_key\n  -> HTTPBearer parses 'Authorization: Bearer ...'\n  -> sha256(token) -> lookup active api_keys row\n  -> found: ClientIdentity   |   not found: 401 UNAUTHORIZED",
                "tip": "Mention auto_error=False: it lets you return your own standardized 401, not FastAPI's default 403.",
            },
            {
                "q": "Q4. Why store only a hash of the key, not the key itself?",
                "level": "MEDIUM",
                "answer": "If the database ever leaks, stored hashes are useless to an attacker, whereas raw "
                          "keys would be instant account takeover. We store sha256(key) and compare hashes on "
                          "each request; the raw key is never persisted anywhere.",
                "simple": "A stolen hash can't be used to call the API; a stolen raw key can.",
                "example": "The seed command reads GATEWAY_API_KEYS, hashes each, and stores only the 64-char "
                           "hex digest. Verified in the DB that no gw_ prefix is stored.",
                "followups": ["Why SHA-256 and not bcrypt/argon2? (next question)"],
            },
            {
                "q": "Q5. Why SHA-256 for API keys instead of bcrypt/argon2 like passwords?",
                "level": "HARD",
                "answer": "Passwords are short and low-entropy, so they need deliberately slow, salted hashing "
                          "to resist brute force. API keys here are long, random, high-entropy secrets, so a "
                          "fast one-way hash is sufficient — and fast matters because we hash on every request. "
                          "Slow hashing would add latency with no real security gain for high-entropy tokens.",
                "simple": "Random long keys don't need slow hashing; passwords do.",
                "example": "gw_ keys are generated with secrets.token_hex, so guessing is infeasible; SHA-256 "
                           "keeps per-request auth cheap.",
                "tip": "This trade-off question is a favorite — the entropy argument is the key insight.",
            },
            {
                "q": "Q6. What is a Bearer token and why 401 (not 403) for a bad key?",
                "level": "EASY",
                "answer": "A Bearer token is a credential sent as-is in the Authorization header — 'whoever "
                          "bears it gets access'. A missing or invalid key means we don't know who you are, "
                          "which is 401 Unauthorized. 403 Forbidden would mean 'we know you but you may not do "
                          "this' — that's authorization/permissions, which is out of V1 scope.",
                "simple": "401 = 'who are you?'. 403 = 'you can't do that'. Bad key is a 401.",
                "example": "AuthenticationError maps to 401 UNAUTHORIZED through the centralized error handler.",
            },
        ],
    },
    {
        "name": "3. Secrets & Design Boundaries",
        "intro": "Configuration, isolation, and what auth deliberately does NOT do.",
        "questions": [
            {
                "q": "Q7. How is authentication kept separate from business logic?",
                "level": "MEDIUM",
                "answer": "All auth lives in one module and is attached as a route dependency. GatewayService "
                          "and the provider adapters never import or know about auth; they only receive data. "
                          "The identity needed for logging is passed in from the route, not pulled into the gateway.",
                "simple": "Auth is a gate in front of the route; the core never sees it.",
                "example": "A grep of services/ and providers/ shows no auth imports; the gateway stays auth-agnostic.",
                "followups": ["Why does that matter? (the gateway can be tested with zero auth/DB setup)"],
            },
            {
                "q": "Q8. What are the security limits of V1, honestly?",
                "level": "MEDIUM",
                "answer": "There is no RBAC/permissions, no rate limiting, no key rotation workflow beyond "
                          "re-seeding, and no per-key quotas. Auth is intentionally authentication-only "
                          "(identity), not authorization. These are deliberate V2 concerns, not bugs.",
                "simple": "V1 answers 'who are you', not 'what are you allowed to do or how much'.",
                "example": "Revoking a key is supported today by setting is_active=false, which makes lookups "
                           "treat it as unknown (401).",
                "tip": "Stating limits plainly builds trust; then mention is_active revocation as the one control you do have.",
            },
        ],
    },
]

build_pdf("03_Authentication_and_Security.pdf",
          "LLM Gateway — Authentication & Security",
          "Interview preparation · V1 · gateway vs provider keys, SHA-256, Bearer auth, secret isolation",
          sections)
