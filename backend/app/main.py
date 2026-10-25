import logging

from fastapi import FastAPI

from app.routers import auth, ingest, users

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)

app = FastAPI(title="Detektor kradzieży drewna")
app.include_router(ingest.router)
app.include_router(auth.router)
app.include_router(users.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
