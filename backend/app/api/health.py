"""Health check endpoint.

A health check is a trivial endpoint that reports whether the service is alive.
It's used by humans (quick sanity check), by Docker/orchestrators (to decide if
a container is ready), and by load balancers (to route traffic only to healthy
instances). It must be cheap and must NOT depend on external services.

We define routes on an APIRouter instead of the main app object. This lets us
group related endpoints per file and register them all in main.py, keeping the
application entrypoint small.
"""

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Return a simple liveness signal.

    `async def` marks this as a coroutine. FastAPI runs it on an event loop,
    which lets the server handle many requests concurrently without blocking.
    For a trivial handler like this it makes no practical difference, but we use
    async consistently because our real endpoints (calling LLM providers over
    the network) will genuinely benefit from it.
    """
    return {"status": "healthy"}
