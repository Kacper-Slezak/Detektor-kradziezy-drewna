"""Powiadomienia Web Push (VAPID) dla leśniczych leśnictwa czujnika (api.md, sekcja 6).

Rodzaje (`type` w treści pusha):
- `alarm`: nowy alarm,
- `low_battery`: bateria właśnie stała się słaba (raz, nie przy każdej ramce),
- `silent`: czujnik nie odzywa się dłużej niż `sensor_silent_after_h`,
- `release_ended`: skończyło się wydanie (wyciszenie), czujnik znów pilnuje mygły.

Dwa pierwsze wywołuje ramka: wysyłka idzie po odpowiedzi na /ingest (BackgroundTasks),
więc płytka nie czeka na usługi push przeglądarek. Dwa ostatnie nie mają ramki, która by je
wywołała, więc sprawdza je pętla `run_periodic_checks` uruchamiana przy starcie aplikacji
(main.py). Zakłada jeden worker uvicorna; przy kilku każdy miałby własną pętlę.

Subskrypcję, o której usługa push mówi 404/410 (wygasła, zgoda cofnięta), usuwamy.
"""

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta

from pywebpush import WebPushException, webpush
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import db
from app.config import settings
from app.models import Alarm, PushSubscription, Release, Sensor, User
from app.services.sensors import as_utc, sensor_statuses

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


# --- treść pushy: service worker pokazuje title i body, a po kliknięciu otwiera url ---


def _label(sensor: Sensor) -> str:
    return sensor.name or sensor.id


def alarm_payload(alarm: Alarm, sensor: Sensor) -> dict:
    what = (
        "Możliwa manipulacja przy czujniku"
        if alarm.possible_tampering
        else "Możliwe podbieranie drewna"
    )
    return {
        "type": "alarm",
        "alarm_id": alarm.id,
        "sensor_id": sensor.id,
        "title": f"Alarm: {_label(sensor)}",
        "body": f"{what}, pewność {alarm.confidence}%",
        "url": f"/alarms/{alarm.id}",
    }


# aplikacja nie ma osobnego adresu czujnika, więc pushe o czujniku otwierają mapę


def low_battery_payload(sensor: Sensor) -> dict:
    return {
        "type": "low_battery",
        "sensor_id": sensor.id,
        "title": f"Słaba bateria: {_label(sensor)}",
        "body": f"Bateria {sensor.battery_pct}%, wymień ją przy najbliższej wizycie",
        "url": "/",
    }


def silent_payload(sensor: Sensor, now: datetime) -> dict:
    hours = int((now - as_utc(sensor.last_seen)).total_seconds() // 3600)
    return {
        "type": "silent",
        "sensor_id": sensor.id,
        "title": f"Brak kontaktu: {_label(sensor)}",
        "body": f"Czujnik nie odzywa się od {hours} h",
        "url": "/",
    }


def release_ended_payload(release: Release, sensor: Sensor) -> dict:
    return {
        "type": "release_ended",
        "sensor_id": sensor.id,
        "release_id": release.id,
        "title": f"Koniec wydania: {_label(sensor)}",
        "body": "Wyciszenie się skończyło, czujnik znów pilnuje mygły",
        "url": "/",
    }


# --- wysyłka ---


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


async def _deliver(session: AsyncSession, sensor: Sensor, payload: dict) -> None:
    """Wysyła do aktywnych leśniczych leśnictwa czujnika i usuwa wygasłe subskrypcje."""
    if not vapid_configured() or sensor.range_id is None:
        return
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

    codes = await asyncio.gather(
        *(
            asyncio.to_thread(
                send_webpush,
                {"endpoint": s.endpoint, "keys": {"p256dh": s.p256dh, "auth": s.auth}},
                payload,
            )
            for s in subscriptions
        )
    )
    gone = [s.id for s, code in zip(subscriptions, codes, strict=True) if code in GONE]
    if gone:
        await session.execute(
            delete(PushSubscription).where(PushSubscription.id.in_(gone))
        )
        await session.commit()
    sent = sum(1 for code in codes if 200 <= code < 300)
    log.info(
        "Push %s (czujnik %s): wysłano %d/%d, usunięto wygasłych %d",
        payload["type"],
        sensor.id,
        sent,
        len(subscriptions),
        len(gone),
    )


async def notify_alarm(alarm_id: int) -> None:
    """Push o nowym alarmie. Nie rzuca wyjątków."""
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
            if row is None:
                return
            alarm, sensor = row
            await _deliver(session, sensor, alarm_payload(alarm, sensor))
    except Exception:
        log.exception("Push o alarmie %s nie powiódł się", alarm_id)


async def notify_low_battery(sensor_id: str) -> None:
    """Push o słabej baterii (o tym, czy już był, decyduje /ingest). Nie rzuca wyjątków."""
    if not vapid_configured():
        return
    try:
        async with db.SessionLocal() as session:
            sensor = await session.get(Sensor, sensor_id)
            if sensor is None or not sensor.active:
                return
            await _deliver(session, sensor, low_battery_payload(sensor))
    except Exception:
        log.exception("Push o baterii czujnika %s nie powiódł się", sensor_id)


async def check_silent_and_ended(now: datetime | None = None) -> None:
    """Jedno przejście: czujniki, które właśnie zamilkły, i wydania, które właśnie się skończyły.

    Flagi zapisujemy przed wysyłką: gdy wysyłka się nie uda, push przepada, ale nie wraca
    co kilka minut. Bez kluczy VAPID flagi też się ustawiają, tylko nic nie wychodzi.
    Nie rzuca wyjątków.
    """
    now = now or datetime.now(UTC)
    try:
        async with db.SessionLocal() as session:
            silent_since = now - timedelta(hours=settings.sensor_silent_after_h)
            candidates = (
                await session.scalars(
                    select(Sensor).where(
                        Sensor.silent_notified.is_(False),
                        # nigdy się nie odezwał = świeżo zamontowany, to jeszcze nie awaria
                        Sensor.last_seen.is_not(None),
                        Sensor.last_seen < silent_since,
                    )
                )
            ).all()
            ended = (
                await session.execute(
                    select(Release, Sensor)
                    .join(Sensor, Release.sensor_id == Sensor.id)
                    .where(Release.end_notified.is_(False), Release.ends_at <= now)
                )
            ).all()

            sensors = {s.id: s for s in candidates} | {s.id: s for _, s in ended}
            states = await sensor_statuses(session, list(sensors.values()), now)
            # wyłączony, z otwartym alarmem albo wyciszony: stan mówi co innego, sprawdzimy później
            silent = [s for s in candidates if states[s.id].state == "silent"]
            for sensor in silent:
                sensor.silent_notified = True
            to_send = []
            for release, sensor in ended:
                release.end_notified = True
                fresh = now - as_utc(release.ends_at) <= timedelta(seconds=PUSH_TTL_S)
                # stare (backend nie działał) albo zaraz po nim następne wydanie: tylko odhaczamy
                if fresh and states[sensor.id].state not in ("inactive", "muted"):
                    to_send.append((release, sensor))
            await session.commit()

            for sensor in silent:
                await _deliver(session, sensor, silent_payload(sensor, now))
            for release, sensor in to_send:
                await _deliver(session, sensor, release_ended_payload(release, sensor))
    except Exception:
        log.exception("Sprawdzanie czujników bez kontaktu i końca wydań nie powiodło się")


async def run_periodic_checks() -> None:
    """Pętla w tle (main.py): co `notify_check_interval_s` jedno przejście."""
    while True:
        await check_silent_and_ended()
        await asyncio.sleep(settings.notify_check_interval_s)
