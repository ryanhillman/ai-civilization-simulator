from fastapi import APIRouter, HTTPException

from app.api.deps import DbSession
from app.domain.simulation_service import SimulationService, seed_world
from app.schemas import CreateWorldRequest, WorldResponse

router = APIRouter()
_svc = SimulationService()


@router.get("", response_model=list[WorldResponse])
async def list_worlds(db: DbSession):
    return await _svc.list_worlds(db)


@router.post("", response_model=WorldResponse, status_code=201)
async def create_world(body: CreateWorldRequest, db: DbSession):
    world = await _svc.create_world(body.name, db)
    return world


@router.get("/{world_id}", response_model=WorldResponse)
async def get_world(world_id: int, db: DbSession):
    try:
        return await _svc.get_world(world_id, db)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/{world_id}/reset", response_model=WorldResponse)
async def reset_world(world_id: int, db: DbSession):
    try:
        return await _svc.reset_world(world_id, db)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
