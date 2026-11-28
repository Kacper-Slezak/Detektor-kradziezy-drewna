import logging
import secrets
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Response,
    Security,
    status,
)
from fastapi.security import APIKeyHeader
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.protocol.decoder import FrameError, decrypt_payload_hex, parse_aes_key
from app.schemas import IngestIn, IngestOut
from app.services.ingest import UnknownSensorError, ingest
from app.services.push import notify_alarm, notify_low_battery

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["ingest"])

ingest_key_header = APIKeyHeader(
    name="X-Ingest-Key",
    auto_error=False,
    description="Klucz urządzeń (`INGEST_API_KEY` z `.env`)",
)

# Sprawdzenie klucza już przy starcie: zły FRAME_AES_KEY zatrzymuje backend od razu.
parse_aes_key(settings.frame_aes_key)
if not settings.frame_aes_key:
    log.warning("FRAME_AES_KEY nie jest ustawiony: ramki z urządzeń przyjmowane bez szyfrowania.")

if not settings.ingest_api_key:
    log.warning(
        "INGEST_API_KEY nie jest ustawiony: POST /api/v1/ingest przyjmuje ramki od każdego. "
        "Ustaw go w .env przed wystawieniem backendu na zewnątrz (tunel, serwer)."
    )


async def require_ingest_key(
    key: Annotated[str | None, Security(ingest_key_header)],
) -> None:
    """401 bez poprawnego klucza. Bez skonfigurowanego klucza przepuszcza wszystko."""
    expected = settings.ingest_api_key
    if not expected:
        return
    if key is None or not secrets.compare_digest(key.encode(), expected.encode()):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Brak lub zły klucz X-Ingest-Key"
        )


@router.post(
    "/ingest",
    response_model=IngestOut,
    status_code=status.HTTP_201_CREATED,
    responses={
        200: {"description": "Duplikat – ramka już była, nic nie zapisano"},
        401: {"description": "Brak lub zły klucz X-Ingest-Key"},
        404: {"description": "Nieznany czujnik"},
        422: {"description": "Błędna ramka"},
    },
)
async def ingest_frame(
    body: IngestIn,
    response: Response,
    background: BackgroundTasks,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[None, Depends(require_ingest_key)],
) -> IngestOut:
    try:
        # przy ustawionym FRAME_AES_KEY: odszyfruj; jawna ramka -> FrameError -> 422
        payload_hex = decrypt_payload_hex(body.payload_hex, parse_aes_key(settings.frame_aes_key))
        result = await ingest(
            session, body.device, payload_hex, body.received_at, body.rssi
        )
    except FrameError as e:
        log.warning("Błędna ramka od %s (%s): %s", body.device, body.payload_hex, e)
        raise HTTPException(422, f"Błędna ramka: {e}") from e
    except UnknownSensorError:
        log.warning("Ramka od nieznanego czujnika: %s", body.device)
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"Nieznany czujnik: {body.device}"
        ) from None

    if result.alarm_created and result.alarm_id is not None:
        # po odpowiedzi: płytka nie czeka na usługi push przeglądarek
        background.add_task(notify_alarm, result.alarm_id)
    if result.low_battery_push:
        background.add_task(notify_low_battery, body.device)

    if result.status == "duplicate":
        response.status_code = status.HTTP_200_OK
    return IngestOut(**result.__dict__)  # low_battery_push pydantic pomija
