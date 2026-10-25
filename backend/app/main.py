import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.db import Base, engine
from app.routers import ingest

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.db_create_all:  # tymczasowo, do czasu migracji Alembic
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(title="Detektor kradzieży drewna", lifespan=lifespan)
app.include_router(ingest.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
