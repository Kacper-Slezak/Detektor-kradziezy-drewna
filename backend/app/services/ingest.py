"""Logika odbioru ramki: czujnik -> dekodowanie -> zapis -> alarm."""

import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)

COUNTER_MOD = 1 << 16  # licznik ma 2 B i się przekręca


class UnknownSensorError(Exception):
    pass


@dataclass
class IngestResult:
    status: str  # "stored" albo "duplicate"
    message_id: int | None = None
    alarm_id: int | None = None
    alarm_created: bool = False
    muted: bool = False


