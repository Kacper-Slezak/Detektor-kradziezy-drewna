"""Recent backend logs for the admin, without shell access to the server.

A logging handler keeps the last MAX_LINES records in memory (deque).
They are lost on container restart/redeploy; for older history use
`docker compose logs web` on the server.
"""

import logging
from collections import deque
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from app.config import settings
from app.deps import AdminUser

MAX_LINES = 2000
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


class LogLine(BaseModel):
    time: datetime
    level: str
    logger: str
    message: str  # with the traceback, if the record had one


class _SkipOkHealth(logging.Filter):
    """Compose healthcheck hits /health every 30 s; those lines would push out the useful ones."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        # uvicorn.access args: (client_addr, method, path, http_version, status_code)
        if isinstance(args, tuple) and len(args) == 5:
            return not (args[2] == "/health" and args[4] == 200)
        return True


class RingBufferHandler(logging.Handler):
    def __init__(self, maxlen: int) -> None:
        super().__init__()
        self.lines: deque[LogLine] = deque(maxlen=maxlen)
        self._fmt = logging.Formatter()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = record.getMessage()
            if record.exc_info:
                message += "\n" + self._fmt.formatException(record.exc_info)
            self.lines.append(
                LogLine(
                    time=datetime.fromtimestamp(record.created, UTC),
                    level=record.levelname,
                    logger=record.name,
                    message=message,
                )
            )
        except Exception:  # noqa: BLE001 - logging.Handler contract: never raise from emit
            self.handleError(record)

    def tail(self, n: int) -> list[LogLine]:
        with self.lock:  # same lock emit() runs under (Handler.handle)
            return list(self.lines)[-n:]


buffer = RingBufferHandler(MAX_LINES)
buffer.addFilter(_SkipOkHealth())


def install() -> None:
    """Attach the buffer to the root logger and to uvicorn's loggers (they don't propagate)."""
    for name in ("", "uvicorn", "uvicorn.access"):
        logger = logging.getLogger(name)
        if buffer not in logger.handlers:
            logger.addHandler(buffer)


@router.get(
    "/logs",
    response_model=list[LogLine],
    responses={404: {"description": "Podgląd logów wyłączony (ADMIN_LOGS_ENABLED=false)"}},
)
async def logs(
    _: AdminUser, tail: Annotated[int, Query(ge=1, le=MAX_LINES)] = 200
) -> list[LogLine]:
    """Last `tail` log records, oldest first."""
    if not settings.admin_logs_enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Podgląd logów jest wyłączony")
    return buffer.tail(tail)
