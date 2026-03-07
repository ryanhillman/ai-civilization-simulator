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
# Routes — registered here as they are implemented in later phases
# ---------------------------------------------------------------------------

# from app.api.routes import world, simulation, agents, timeline, events
# app.include_router(world.router, prefix="/api/world", tags=["world"])
# app.include_router(simulation.router, prefix="/api/simulation", tags=["simulation"])
# app.include_router(agents.router, prefix="/api/agents", tags=["agents"])
# app.include_router(timeline.router, prefix="/api/timeline", tags=["timeline"])
# app.include_router(events.router, prefix="/api/events", tags=["events"])


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
