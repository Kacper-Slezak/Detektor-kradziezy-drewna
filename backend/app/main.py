from fastapi import FastAPI

app = FastAPI(title="Detektor kradzieży drewna")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
