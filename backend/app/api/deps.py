from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db

# Convenience type alias used in route signatures:
#   async def my_route(db: DbSession) -> ...
DbSession = Annotated[AsyncSession, Depends(get_db)]
