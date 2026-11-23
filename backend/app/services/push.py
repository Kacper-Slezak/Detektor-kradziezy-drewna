"""Powiadomienia Web Push (VAPID) o nowym alarmie.

Wysyłka idzie po odpowiedzi na /ingest (BackgroundTasks), więc płytka nie czeka na usługi
push przeglądarek. Dostają ją leśniczowie leśnictwa czujnika (api.md, sekcja 6).
Subskrypcję, o której usługa push mówi 404/410 (wygasła, zgoda cofnięta), usuwamy.
"""

import asyncio
import json
import logging

from pywebpush import WebPushException, webpush
from sqlalchemy import delete, select

from app import db
from app.config import settings
from app.models import Alarm, PushSubscription, Sensor, User

log = logging.getLogger(__name__)

PUSH_TTL_S = 3600  # po godzinie alarm przestaje być pilny, usługa push może go porzucić
SEND_TIMEOUT_S = 10
GONE = (404, 410)


def vapid_configured() -> bool:
    return bool(
        settings.vapid_private_key
        and settings.vapid_public_key
        and settings.vapid_subject
    )


def alarm_payload(alarm: Alarm, sensor: Sensor) -> dict:
    """Treść pusha: service worker pokazuje title i body, a po kliknięciu otwiera url."""
    tampering = alarm.sources == ["vibration"]
    what = (
        "Możliwa manipulacja przy czujniku"
        if tampering
        else "Możliwe podbieranie drewna"
    )
    return {
        "type": "alarm",
        "alarm_id": alarm.id,
        "sensor_id": sensor.id,
        "title": f"Alarm: {sensor.name or sensor.id}",
        "body": f"{what}, pewność {alarm.confidence}%",
        "url": f"/alarms/{alarm.id}",
    }


def send_webpush(info: dict, payload: dict) -> int:
    """Jedna wysyłka (blokująca; wołana w wątku). Zwraca kod HTTP usługi push, 0 = brak łączności."""
    try:
        response = webpush(
            subscription_info=info,
            data=json.dumps(payload, ensure_ascii=False),
            vapid_private_key=settings.vapid_private_key,
            vapid_claims={
                "sub": settings.vapid_subject
            },  # pywebpush dopisuje do niego aud i exp
            ttl=PUSH_TTL_S,
            timeout=SEND_TIMEOUT_S,
        )
        return response.status_code
    except WebPushException as e:
        return e.response.status_code if e.response is not None else 0
    except Exception as e:  # noqa: BLE001 - zły klucz, błąd sieci itp. nie mogą wywrócić zadania
        log.error("Push: wysyłka nie powiodła się: %s", e)
        return 0


async def notify_alarm(alarm_id: int) -> None:
    """Wysyła push o alarmie do leśniczych jego leśnictwa. Nie rzuca wyjątków."""
    if not vapid_configured():
        return
    try:
        async with db.SessionLocal() as session:
            row = (
                await session.execute(
                    select(Alarm, Sensor)
                    .join(Sensor, Alarm.sensor_id == Sensor.id)
                    .where(Alarm.id == alarm_id)
                )
            ).first()
            if row is None or row[1].range_id is None:
                return
            alarm, sensor = row
            subscriptions = (
                await session.scalars(
                    select(PushSubscription)
                    .join(User, PushSubscription.user_id == User.id)
                    .where(
                        User.role == "forester",
                        User.active.is_(True),
                        User.range_id == sensor.range_id,
                    )
                )
            ).all()
            if not subscriptions:
                return

            payload = alarm_payload(alarm, sensor)
            codes = await asyncio.gather(
                *(
                    asyncio.to_thread(
                        send_webpush,
                        {
                            "endpoint": s.endpoint,
                            "keys": {"p256dh": s.p256dh, "auth": s.auth},
                        },
                        payload,
                    )
                    for s in subscriptions
                )
            )
            gone = [
                s.id
                for s, code in zip(subscriptions, codes, strict=True)
                if code in GONE
            ]
            if gone:
                await session.execute(
                    delete(PushSubscription).where(PushSubscription.id.in_(gone))
                )
                await session.commit()
            sent = sum(1 for code in codes if 200 <= code < 300)
            log.info(
                "Push o alarmie %s: wysłano %d/%d, usunięto wygasłych %d",
                alarm_id,
                sent,
                len(subscriptions),
                len(gone),
            )
    except Exception:
        log.exception("Push o alarmie %s nie powiódł się", alarm_id)
