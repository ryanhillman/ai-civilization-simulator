import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="AI Civilization Simulator",
    description="Turn-based medieval village simulation with selective LLM interpretation",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

from app.api.routes import agents, ai as ai_routes, simulation, timeline, worlds  # noqa: E402

app.include_router(worlds.router, prefix="/api/worlds", tags=["worlds"])
app.include_router(simulation.router, prefix="/api/worlds", tags=["simulation"])
app.include_router(agents.router, prefix="/api/worlds", tags=["agents"])
app.include_router(timeline.router, prefix="/api/worlds", tags=["timeline"])
app.include_router(ai_routes.router, prefix="/api/worlds", tags=["ai"])


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@app.get("/api/health", tags=["system"])
async def health() -> dict:
    return {"status": "ok", "env": settings.app_env}


# ---------------------------------------------------------------------------
# Startup log
# ---------------------------------------------------------------------------


@app.on_event("startup")
async def on_startup() -> None:
    logger.info("AI Civilization Simulator starting up [env=%s]", settings.app_env)
    # --- DIAGNOSTIC: remove after confirming AI config ---
    key = settings.azure_openai_key
    key_preview = key[:5] if key else "(empty)"
    print(f"[DIAG] ai_enabled={settings.ai_enabled!r}")
    print(f"[DIAG] azure_openai_key prefix={key_preview!r} (len={len(key)})")
    print(f"[DIAG] azure_openai_endpoint={settings.azure_openai_endpoint!r}")
    print(f"[DIAG] azure_openai_deployment_name={settings.azure_openai_deployment_name!r}")
    # --- END DIAGNOSTIC ---
