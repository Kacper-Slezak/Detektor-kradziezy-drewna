import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.routers import admin, alarms, auth, ingest, push, releases, reports, sensors, users
from app.services.push import run_periodic_checks

logging.basicConfig(level=logging.INFO, format=admin.LOG_FORMAT)
admin.install()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Pętla pushy bez ramki (brak kontaktu, koniec wydania) żyje tyle, co aplikacja."""
    task = asyncio.create_task(run_periodic_checks())
    yield
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task


app = FastAPI(title="Detektor kradzieży drewna", lifespan=lifespan)
app.include_router(ingest.router)
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(sensors.router)
app.include_router(alarms.router)
app.include_router(releases.router)
app.include_router(reports.router)
app.include_router(push.router)
app.include_router(admin.router)


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
