"""Recent backend logs for the admin, without shell access to the server.

A logging handler keeps the last MAX_LINES formatted lines in memory (deque).
Lines are lost on container restart/redeploy; for older history use
`docker compose logs web` on the server.
"""

import logging
from collections import deque
from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.responses import PlainTextResponse

from app.deps import AdminUser

MAX_LINES = 2000
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


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
        self.lines: deque[str] = deque(maxlen=maxlen)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.lines.append(self.format(record))
        except Exception:
            self.handleError(record)

    def tail(self, n: int) -> list[str]:
        with self.lock:  # same lock emit() runs under (Handler.handle)
            return list(self.lines)[-n:]


buffer = RingBufferHandler(MAX_LINES)
buffer.setFormatter(logging.Formatter(LOG_FORMAT))
buffer.addFilter(_SkipOkHealth())


def install() -> None:
    """Attach the buffer to the root logger and to uvicorn's loggers (they don't propagate)."""
    for name in ("", "uvicorn", "uvicorn.access"):
        logger = logging.getLogger(name)
        if buffer not in logger.handlers:
            logger.addHandler(buffer)


@router.get("/logs", response_class=PlainTextResponse)
async def logs(
    _: AdminUser, tail: Annotated[int, Query(ge=1, le=MAX_LINES)] = 200
) -> str:
    """Last `tail` lines of the backend log, oldest first, as plain text."""
    return "\n".join(buffer.tail(tail)) + "\n"
