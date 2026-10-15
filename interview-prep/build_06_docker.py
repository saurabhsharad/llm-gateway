from engine import build_pdf

sections = [
    {
        "name": "1. The Docker Stack",
        "intro": "Three containers, one command.",
        "questions": [
            {
                "q": "Q1. Describe your Docker setup.",
                "level": "EASY",
                "answer": "Three services via Docker Compose: postgres (PostgreSQL 16 with a persistent named "
                          "volume), backend (FastAPI/uvicorn), and frontend (React built, served by nginx). "
                          "One command, 'docker compose up --build', runs the whole stack with no host Python, "
                          "Node, or Postgres required.",
                "simple": "postgres + backend + frontend, started together with one command.",
                "code": "Browser -> localhost:3000 -> frontend (nginx)\nBrowser -> localhost:8000 -> backend (FastAPI)\nbackend -> postgres:5432 -> PostgreSQL",
                "tip": "Lead with 'three services, one command, nothing needed on the host'.",
            },
            {
                "q": "Q2. Why three separate containers instead of one?",
                "level": "MEDIUM",
                "answer": "They have different runtimes and lifecycles (Python vs Node/nginx vs a database), "
                          "should scale and restart independently, and one-container-does-everything is an "
                          "anti-pattern. Separate images stay small and mirror a realistic deployment topology.",
                "simple": "Different jobs, different runtimes — keep them isolated.",
                "followups": ["Trade-off? (slightly more orchestration config, but far cleaner separation)"],
            },
            {
                "q": "Q3. Why is PostgreSQL in a container with a named volume?",
                "level": "EASY",
                "answer": "So nobody needs to install Postgres locally, and the named volume persists data "
                          "across container restarts and rebuilds. 'docker compose down' keeps the volume; "
                          "'down -v' deletes it for a clean slate.",
                "simple": "Containerized DB for easy setup; the volume keeps data safe between restarts.",
                "example": "The seeded gateway key and logged requests survive a normal down/up because the "
                           "pgdata volume is retained.",
            },
        ],
    },
    {
        "name": "2. Startup & Networking",
        "intro": "How the containers find each other and come up safely.",
        "questions": [
            {
                "q": "Q4. How does the backend connect to PostgreSQL in Docker?",
                "level": "MEDIUM",
                "answer": "By the Docker service name, not localhost. Compose injects DATABASE_URL as "
                          "postgresql+psycopg://...@postgres:5432/... so the backend resolves 'postgres' on the "
                          "Compose network. This overrides any localhost value in the local .env.",
                "simple": "Inside Docker, 'postgres' is the hostname; 'localhost' would be the backend itself.",
                "code": "DATABASE_URL=postgresql+psycopg://gateway:***@postgres:5432/gateway",
                "tip": "Service-name DNS on the Compose network is the key concept here.",
            },
            {
                "q": "Q5. Why is the frontend built with http://localhost:8000 and NOT http://backend:8000?",
                "level": "HARD",
                "answer": "Because the code that calls the backend runs in the user's BROWSER, not inside a "
                          "container. The browser can't resolve the Docker-internal name 'backend'; it reaches "
                          "the backend through the published host port localhost:8000. So VITE_API_BASE_URL is a "
                          "build-time value pointing at the host-reachable URL.",
                "simple": "The browser is outside Docker, so it uses localhost, not the internal service name.",
                "example": "We verified the built bundle contains http://localhost:8000 and not http://backend:8000.",
                "followups": ["Why is it build-time? (Vite inlines import.meta.env at build, so it must be set before npm run build)"],
                "tip": "This 'browser is outside the network' insight is a classic Docker gotcha — nail it.",
            },
            {
                "q": "Q6. How do you guarantee the DB is ready and migrated before serving?",
                "level": "MEDIUM",
                "answer": "Postgres has a pg_isready healthcheck; the backend depends_on postgres with "
                          "condition: service_healthy, so it starts only once the DB is healthy. The backend "
                          "entrypoint then runs 'alembic upgrade head' before uvicorn, with set -e so a failed "
                          "migration stops the container instead of serving a broken schema.",
                "simple": "Wait for DB healthy -> migrate -> only then start the server.",
                "code": "postgres healthy -> backend starts -> alembic upgrade head -> uvicorn 0.0.0.0:8000",
                "followups": ["What binds uvicorn to 0.0.0.0? (so the server is reachable from outside the container, not just inside)"],
            },
        ],
    },
    {
        "name": "3. Serving, Health & Secrets",
        "intro": "Production serving, health checks, and keeping secrets out of images.",
        "questions": [
            {
                "q": "Q7. Why serve the frontend with nginx (multi-stage build) instead of 'vite preview'?",
                "level": "MEDIUM",
                "answer": "Stage 1 uses Node to run 'npm ci' and 'npm run build' into static files; stage 2 "
                          "copies only those files into a small nginx image to serve them. nginx is a real, "
                          "efficient static server; 'vite preview' is a dev tool, not meant for production. "
                          "Multi-stage also keeps Node and node_modules out of the final image.",
                "simple": "Build with Node, ship only the static files on nginx — small and production-appropriate.",
                "example": "nginx also serves a /healthz endpoint used as the container healthcheck, and uses an "
                           "SPA fallback to index.html.",
                "followups": ["Why did the healthcheck initially fail? (busybox wget resolved localhost to IPv6; fixed by using 127.0.0.1)"],
            },
            {
                "q": "Q8. How are secrets kept out of images and the build context?",
                "level": "HARD",
                "answer": "Secrets come from the gitignored backend/.env via Compose env_file at runtime, never "
                          "baked into images. .dockerignore files exclude .env, .venv, node_modules, dist, "
                          "caches and .git from the build context. Only the non-secret VITE_API_BASE_URL is "
                          "passed as a frontend build arg. We scanned the frontend bundle and image to confirm "
                          "no provider or gateway keys are present.",
                "simple": "Secrets are injected at runtime, excluded from build context, and never in the frontend.",
                "example": "docker compose ps shows all three services healthy; the backend reads keys from "
                           "env_file, while the frontend image contains only static files.",
                "tip": "Mention .dockerignore explicitly — it's an easy way to accidentally ship .env if forgotten.",
            },
        ],
    },
]

build_pdf("06_Docker_and_Deployment.pdf",
          "LLM Gateway — Docker & Deployment",
          "Interview preparation · V1 · three-service Compose stack, migrations-before-serve, secret isolation",
          sections)
