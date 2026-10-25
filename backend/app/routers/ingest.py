import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.protocol.decoder import FrameError
from app.schemas import IngestIn, IngestOut
from app.services.ingest import UnknownSensorError, ingest

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["ingest"])


@router.post(
    "/ingest",
    response_model=IngestOut,
    status_code=status.HTTP_201_CREATED,
    responses={
        200: {"description": "Duplikat – ramka już była, nic nie zapisano"},
        404: {"description": "Nieznany czujnik"},
        422: {"description": "Błędna ramka"},
    },
)
async def ingest_frame(
    body: IngestIn,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> IngestOut:
    try:
        result = await ingest(session, body.device, body.payload_hex, body.received_at, body.rssi)
    except FrameError as e:
        log.warning("Błędna ramka od %s (%s): %s", body.device, body.payload_hex, e)
        raise HTTPException(422, f"Błędna ramka: {e}") from e
    except UnknownSensorError:
        log.warning("Ramka od nieznanego czujnika: %s", body.device)
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Nieznany czujnik: {body.device}") from None

    if result.status == "duplicate":
        response.status_code = status.HTTP_200_OK
    return IngestOut(**result.__dict__)
