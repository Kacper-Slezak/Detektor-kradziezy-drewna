import logging
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.routers import alarms, auth, ingest, releases, sensors, users

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)

app = FastAPI(title="Detektor kradzieży drewna")
app.include_router(ingest.router)
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(sensors.router)
app.include_router(alarms.router)
app.include_router(releases.router)


log = logging.getLogger(__name__)


@app.get("/health", responses={503: {"description": "Baza danych niedostępna"}})
async def health(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, str]:
    """Dla monitoringu i compose: `ok` tylko wtedy, gdy backend dogaduje się z bazą."""
    try:
        await session.execute(text("SELECT 1"))
    except (SQLAlchemyError, OSError) as e:
        log.error("Health: baza niedostępna: %s", e)
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Baza danych niedostępna"
        )
    return {"status": "ok"}
