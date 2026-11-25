"""Powiadomienia Web Push: subskrypcje (api.md, sekcja 6) i wysyłka: alarm, bateria, brak kontaktu, koniec wydania."""

import base64
import json
from datetime import UTC, datetime, timedelta

import pytest
import requests
from sqlalchemy import delete, select

from app import db
from app.config import settings
from app.models import Alarm, PushSubscription, Range, Release, Sensor, User
from app.protocol.encoder import encode_heartbeat
from app.services import push
from tests.conftest import SENSOR_ID
from tests.utils import auth
from tools.generate_vapid_keys import generate

ALARM_FRAME = "11002a0101570028b440"  # ALARM, licznik 42, mikrofon, pewność 87%
EP1 = "https://fcm.googleapis.com/fcm/send/aaa"
EP2 = "https://updates.push.services.mozilla.com/wpush/v2/bbb"
KEYS = {
    "p256dh": "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QTpQtUbVlUls0VJXg7A8u-Ts1XbjhazAkj7I99e8QcYP7DkM",
    "auth": "tBHItJI5svbpez7KI4CCXg",
}


def body(endpoint=EP1, **extra):
    return {
        "endpoint": endpoint,
        "keys": KEYS,
        "device_label": "Android – Chrome",
        **extra,
    }


@pytest.fixture
def vapid(monkeypatch):
    public, private = generate()
    monkeypatch.setattr(settings, "vapid_public_key", public)
    monkeypatch.setattr(settings, "vapid_private_key", private)
    monkeypatch.setattr(settings, "vapid_subject", "mailto:test@example.com")
    return public, private


@pytest.fixture
async def ranges(session_maker) -> tuple[int, int]:
    """Dąbrowa (z czujnikiem testowym) i Olszyny."""
    async with session_maker() as s:
        dabrowa, olszyny = (
            Range(name="Leśnictwo Dąbrowa"),
            Range(name="Leśnictwo Olszyny"),
        )
        s.add_all([dabrowa, olszyny])
        await s.flush()
        (await s.get(Sensor, SENSOR_ID)).range_id = dabrowa.id
        await s.commit()
        return dabrowa.id, olszyny.id


@pytest.fixture
async def forester(client, make_user, ranges):
    await make_user("blazej", range_id=ranges[0])
    return await auth(client, "blazej")


async def subscriptions(session_maker) -> list[PushSubscription]:
    async with session_maker() as s:
        return list(
            (
                await s.scalars(select(PushSubscription).order_by(PushSubscription.id))
            ).all()
        )


# --- klucz publiczny ---


async def test_klucz_publiczny(client, forester, vapid):
    r = await client.get("/api/v1/push/vapid-public-key", headers=forester)
    assert r.status_code == 200
    assert r.json() == {"public_key": vapid[0]}


async def test_klucz_publiczny_bez_konfiguracji_503(client, forester, monkeypatch):
    monkeypatch.setattr(settings, "vapid_public_key", "")
    r = await client.get("/api/v1/push/vapid-public-key", headers=forester)
    assert r.status_code == 503


async def test_klucz_publiczny_wymaga_logowania(client):
    assert (await client.get("/api/v1/push/vapid-public-key")).status_code == 401


# --- subskrypcje ---


async def test_zapis_subskrypcji(client, forester, session_maker):
    r = await client.post(
        "/api/v1/push/subscriptions", headers=forester, json=body(expirationTime=None)
    )
    assert r.status_code == 201
    [sub] = await subscriptions(session_maker)
    assert r.json() == {"id": sub.id}
    assert (sub.endpoint, sub.p256dh, sub.auth) == (EP1, KEYS["p256dh"], KEYS["auth"])
    assert sub.device_label == "Android – Chrome"


async def test_ten_sam_endpoint_nadpisuje_bez_duplikatu(
    client, forester, make_user, ranges, session_maker
):
    await client.post("/api/v1/push/subscriptions", headers=forester, json=body())
    await make_user("ola", range_id=ranges[1])
    ola = await auth(client, "ola")

    new_keys = {"p256dh": "inny-klucz", "auth": "inny-sekret"}
    r = await client.post(
        "/api/v1/push/subscriptions",
        headers=ola,
        json={"endpoint": EP1, "keys": new_keys, "device_label": "Telefon Oli"},
    )
    assert r.status_code == 201
    [sub] = await subscriptions(session_maker)  # nadal jedna
    assert (sub.p256dh, sub.auth, sub.device_label) == (
        "inny-klucz",
        "inny-sekret",
        "Telefon Oli",
    )
    async with session_maker() as s:
        ola_id = await s.scalar(select(User.id).where(User.login == "ola"))
    assert sub.user_id == ola_id  # telefon przeszedł na inne konto


async def test_tylko_lesniczy_subskrybuje(client, make_user, ranges):
    await make_user("bogdan", role="district_manager")
    await make_user("admin", role="admin")
    for login in ("bogdan", "admin"):
        r = await client.post(
            "/api/v1/push/subscriptions", headers=await auth(client, login), json=body()
        )
        assert r.status_code == 403


@pytest.mark.parametrize(
    "payload",
    [
        {"endpoint": "http://nie-https.example/x", "keys": KEYS},  # tylko https
        {"endpoint": EP1},  # brak kluczy
        {"endpoint": EP1, "keys": {"p256dh": "x"}},  # brak auth
        {"keys": KEYS},  # brak endpointu
    ],
)
async def test_zle_dane_422(client, forester, payload):
    assert (
        await client.post("/api/v1/push/subscriptions", headers=forester, json=payload)
    ).status_code == 422


async def test_zapis_wymaga_logowania(client):
    assert (
        await client.post("/api/v1/push/subscriptions", json=body())
    ).status_code == 401


async def test_usuniecie_wlasnej_subskrypcji(client, forester, session_maker):
    await client.post("/api/v1/push/subscriptions", headers=forester, json=body(EP1))
    await client.post("/api/v1/push/subscriptions", headers=forester, json=body(EP2))
    r = await client.delete(
        "/api/v1/push/subscriptions", headers=forester, params={"endpoint": EP1}
    )
    assert r.status_code == 204
    assert [s.endpoint for s in await subscriptions(session_maker)] == [EP2]


async def test_usuniecie_nieistniejacej_to_204(client, forester):
    r = await client.delete(
        "/api/v1/push/subscriptions", headers=forester, params={"endpoint": EP1}
    )
    assert r.status_code == 204


async def test_cudzej_subskrypcji_nie_usunie(
    client, forester, make_user, ranges, session_maker
):
    await client.post("/api/v1/push/subscriptions", headers=forester, json=body())
    await make_user("ola", range_id=ranges[0])
    r = await client.delete(
        "/api/v1/push/subscriptions",
        headers=await auth(client, "ola"),
        params={"endpoint": EP1},
    )
    assert r.status_code == 204
    assert len(await subscriptions(session_maker)) == 1


# --- wysyłka ---


@pytest.fixture
def sent(monkeypatch, session_maker, vapid):
    """Zamiast prawdziwej wysyłki: zapisuje, co poszło dokąd; kod odpowiedzi usługi push do ustawienia."""
    calls: list[tuple[str, dict]] = []
    codes: dict[str, int] = {}

    def fake(info: dict, payload: dict) -> int:
        calls.append((info["endpoint"], payload))
        return codes.get(info["endpoint"], 201)

    monkeypatch.setattr(push, "send_webpush", fake)
    monkeypatch.setattr(
        db, "SessionLocal", session_maker
    )  # zadanie w tle ma własną sesję
    fake.codes = codes
    fake.calls = calls
    return fake


async def make_alarm(session_maker) -> int:
    from datetime import UTC, datetime

    async with session_maker() as s:
        alarm = Alarm(
            sensor_id=SENSOR_ID,
            started_at=datetime.now(UTC),
            last_frame_at=datetime.now(UTC),
            event_type=1,
            sources=["microphone", "vibration"],
            confidence=87,
            duration_s=40,
            energy=180,
        )
        s.add(alarm)
        await s.commit()
        return alarm.id


async def add_sub(session_maker, login, endpoint):
    async with session_maker() as s:
        user_id = await s.scalar(select(User.id).where(User.login == login))
        s.add(
            PushSubscription(endpoint=endpoint, p256dh="k", auth="a", user_id=user_id)
        )
        await s.commit()


async def test_push_trafia_do_lesniczych_leśnictwa_czujnika(
    sent, session_maker, make_user, ranges
):
    await make_user("blazej", range_id=ranges[0])
    await make_user("ola", range_id=ranges[1])  # inne leśnictwo
    await make_user(
        "bogdan", role="district_manager"
    )  # nadleśniczy: raporty, bez pushy
    await make_user("nieaktywny", range_id=ranges[0], active=False)
    for login, ep in [
        ("blazej", EP1),
        ("ola", EP2),
        ("bogdan", "https://x/b"),
        ("nieaktywny", "https://x/n"),
    ]:
        await add_sub(session_maker, login, ep)

    alarm_id = await make_alarm(session_maker)
    await push.notify_alarm(alarm_id)

    assert [ep for ep, _ in sent.calls] == [EP1]
    assert sent.calls[0][1] == {
        "type": "alarm",
        "alarm_id": alarm_id,
        "sensor_id": SENSOR_ID,
        "title": "Alarm: Skład przy drodze 5",
        "body": "Możliwe podbieranie drewna, pewność 87%",
        "url": f"/alarms/{alarm_id}",
    }


async def test_same_wibracje_to_mozliwa_manipulacja(
    sent, session_maker, make_user, ranges
):
    await make_user("blazej", range_id=ranges[0])
    await add_sub(session_maker, "blazej", EP1)
    alarm_id = await make_alarm(session_maker)
    async with session_maker() as s:
        (await s.get(Alarm, alarm_id)).sources = ["vibration"]
        await s.commit()

    await push.notify_alarm(alarm_id)
    assert sent.calls[0][1]["body"] == "Możliwa manipulacja przy czujniku, pewność 87%"


@pytest.mark.parametrize("code", [404, 410])
async def test_wygasla_subskrypcja_jest_usuwana(
    sent, session_maker, make_user, ranges, code
):
    await make_user("blazej", range_id=ranges[0])
    await add_sub(session_maker, "blazej", EP1)
    await add_sub(session_maker, "blazej", EP2)
    sent.codes[EP1] = code

    await push.notify_alarm(await make_alarm(session_maker))
    assert [s.endpoint for s in await subscriptions(session_maker)] == [EP2]


@pytest.mark.parametrize("code", [0, 429, 500, 503])
async def test_chwilowy_blad_nie_usuwa_subskrypcji(
    sent, session_maker, make_user, ranges, code
):
    await make_user("blazej", range_id=ranges[0])
    await add_sub(session_maker, "blazej", EP1)
    sent.codes[EP1] = code

    await push.notify_alarm(await make_alarm(session_maker))
    assert len(await subscriptions(session_maker)) == 1


async def test_bez_konfiguracji_vapid_nic_nie_wysyla(
    sent, session_maker, make_user, ranges, monkeypatch
):
    monkeypatch.setattr(settings, "vapid_private_key", "")
    await make_user("blazej", range_id=ranges[0])
    await add_sub(session_maker, "blazej", EP1)

    await push.notify_alarm(await make_alarm(session_maker))
    assert sent.calls == []


async def test_czujnik_bez_lesnictwa_nikogo_nie_budzi(
    sent, session_maker, make_user, ranges
):
    await make_user("blazej", range_id=ranges[0])
    await add_sub(session_maker, "blazej", EP1)
    alarm_id = await make_alarm(session_maker)
    async with session_maker() as s:
        (await s.get(Sensor, SENSOR_ID)).range_id = None
        await s.commit()

    await push.notify_alarm(alarm_id)
    assert sent.calls == []


async def test_blad_w_zadaniu_nie_wychodzi_na_zewnatrz(
    sent, session_maker, make_user, ranges, monkeypatch
):
    await make_user("blazej", range_id=ranges[0])
    await add_sub(session_maker, "blazej", EP1)

    def boom(*_):
        raise RuntimeError("awaria")

    monkeypatch.setattr(push, "send_webpush", boom)
    await push.notify_alarm(await make_alarm(session_maker))  # nie rzuca


# --- ingest uruchamia wysyłkę ---


async def post_frame(client, payload_hex):
    return await client.post(
        "/api/v1/ingest", json={"device": SENSOR_ID, "payload_hex": payload_hex}
    )


async def test_nowy_alarm_z_ingest_wysyla_push_raz(
    client, sent, session_maker, make_user, ranges
):
    await make_user("blazej", range_id=ranges[0])
    await add_sub(session_maker, "blazej", EP1)

    r = await post_frame(client, ALARM_FRAME)
    assert r.status_code == 201 and r.json()["alarm_created"] is True
    assert len(sent.calls) == 1
    assert sent.calls[0][1]["alarm_id"] == r.json()["alarm_id"]

    # powtórzenie ALARM scala się z tym alarmem, więc drugiego pusha nie ma
    r = await post_frame(client, "11002b0101570028b440")
    assert r.json()["alarm_created"] is False
    assert len(sent.calls) == 1


async def test_wyciszony_czujnik_nie_wysyla_pusha(
    client, sent, session_maker, make_user, ranges
):
    await make_user("blazej", range_id=ranges[0])
    await add_sub(session_maker, "blazej", EP1)
    async with session_maker() as s:
        (await s.get(Sensor, SENSOR_ID)).active = False
        await s.commit()

    r = await post_frame(client, ALARM_FRAME)
    assert r.json()["muted"] is True
    assert sent.calls == []


# --- prawdziwa biblioteka: szyfrowanie i podpis VAPID bez sieci ---


def test_prawdziwa_wysylka_jest_odszyfrowywalna_i_podpisana(monkeypatch, vapid):
    """Przeglądarka (tu: http_ece z kluczem odbiorcy) musi odczytać wiadomość, a podpis VAPID musi się zgadzać."""
    import http_ece
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from py_vapid import Vapid02

    receiver = ec.generate_private_key(ec.SECP256R1())
    auth_secret = b"0123456789abcdef"
    b64 = lambda raw: base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
    info = {
        "endpoint": "https://push.example/send/xyz",
        "keys": {
            "p256dh": b64(
                receiver.public_key().public_bytes(
                    serialization.Encoding.X962,
                    serialization.PublicFormat.UncompressedPoint,
                )
            ),
            "auth": b64(auth_secret),
        },
    }
    captured = {}

    def fake_post(url, data=None, headers=None, timeout=None, **_):
        captured.update(url=url, data=data, headers=headers)
        response = requests.Response()
        response.status_code = 201
        return response

    monkeypatch.setattr(requests, "post", fake_post)
    payload = {
        "type": "alarm",
        "alarm_id": 41,
        "title": "Alarm: Składzik ąęł",
        "body": "x",
        "url": "/alarms/41",
    }

    assert push.send_webpush(info, payload) == 201

    assert captured["url"] == "https://push.example/send/xyz"
    assert captured["headers"]["content-encoding"] == "aes128gcm"
    assert captured["headers"]["ttl"] == str(push.PUSH_TTL_S)
    plain = http_ece.decrypt(
        captured["data"],
        private_key=receiver,
        auth_secret=auth_secret,
        version="aes128gcm",
    )
    assert json.loads(plain) == payload

    scheme, _, params = captured["headers"]["authorization"].partition(" ")
    assert scheme.lower() == "vapid"
    claims = dict(p.split("=", 1) for p in params.split(","))
    assert claims["k"] == vapid[0]  # klucz publiczny z naszej pary
    assert Vapid02.verify(
        captured["headers"]["authorization"]
    )  # podpis JWT zgodny z kluczem k
    jwt_payload = claims["t"].split(".")[1]
    jwt_claims = json.loads(
        base64.urlsafe_b64decode(jwt_payload + "=" * (-len(jwt_payload) % 4))
    )
    assert jwt_claims["sub"] == "mailto:test@example.com"
    assert jwt_claims["aud"] == "https://push.example"


# --- słaba bateria (z /ingest) ---


def heartbeat(counter, battery, low_flag=False):
    return encode_heartbeat(counter, battery_pct=battery, low_battery=low_flag).hex()


async def test_slaba_bateria_push_raz_i_znowu_po_wymianie(
    client, sent, session_maker, make_user, ranges
):
    await make_user("blazej", range_id=ranges[0])
    await add_sub(session_maker, "blazej", EP1)

    for counter, battery in enumerate([50, 15, 14, 22, 18], start=1):
        await post_frame(client, heartbeat(counter, battery))
    # 15 %: push; 14 %: już był; 22 % to za mało, żeby uznać baterię za dobrą (próg + 5)
    assert [p["type"] for _, p in sent.calls] == ["low_battery"]
    assert sent.calls[0][1] == {
        "type": "low_battery",
        "sensor_id": SENSOR_ID,
        "title": "Słaba bateria: Skład przy drodze 5",
        "body": "Bateria 15%, wymień ją przy najbliższej wizycie",
        "url": f"/sensors/{SENSOR_ID}",
    }

    await post_frame(client, heartbeat(6, 90))  # nowa bateria
    await post_frame(client, heartbeat(7, 12))
    assert [p["body"] for _, p in sent.calls][1] == (
        "Bateria 12%, wymień ją przy najbliższej wizycie"
    )
    assert len(sent.calls) == 2


async def test_flaga_slabej_baterii_z_heartbeatu(
    client, sent, session_maker, make_user, ranges
):
    await make_user("blazej", range_id=ranges[0])
    await add_sub(session_maker, "blazej", EP1)

    r = await post_frame(client, heartbeat(1, 40, low_flag=True))
    assert r.status_code == 201 and "low_battery_push" not in r.json()
    assert [p["type"] for _, p in sent.calls] == ["low_battery"]


# --- brak kontaktu i koniec wydania (pętla w tle) ---


async def set_last_seen(session_maker, when):
    async with session_maker() as s:
        (await s.get(Sensor, SENSOR_ID)).last_seen = when
        await s.commit()


async def add_release(session_maker, starts_at, ends_at) -> int:
    async with session_maker() as s:
        release = Release(sensor_id=SENSOR_ID, starts_at=starts_at, ends_at=ends_at)
        s.add(release)
        await s.commit()
        return release.id


async def test_brak_kontaktu_push_raz_i_znowu_po_nastepnej_ciszy(
    client, sent, session_maker, make_user, ranges
):
    await make_user("blazej", range_id=ranges[0])
    await add_sub(session_maker, "blazej", EP1)
    now = datetime.now(UTC)
    await set_last_seen(session_maker, now - timedelta(hours=11))

    await push.check_silent_and_ended(now)  # 11 h < 12 h: jeszcze nie
    assert sent.calls == []

    await set_last_seen(session_maker, now - timedelta(hours=13))
    await push.check_silent_and_ended(now)
    await push.check_silent_and_ended(now)  # drugie przejście nie powtarza
    assert [p for _, p in sent.calls] == [
        {
            "type": "silent",
            "sensor_id": SENSOR_ID,
            "title": "Brak kontaktu: Skład przy drodze 5",
            "body": "Czujnik nie odzywa się od 13 h",
            "url": f"/sensors/{SENSOR_ID}",
        }
    ]

    await post_frame(client, heartbeat(1, 80))  # odezwał się: flaga kasowana
    await set_last_seen(session_maker, now - timedelta(hours=20))
    await push.check_silent_and_ended(now)
    assert len(sent.calls) == 2


async def test_brak_kontaktu_nie_dla_nowego_wylaczonego_ani_wyciszonego(
    sent, session_maker, make_user, ranges
):
    await make_user("blazej", range_id=ranges[0])
    await add_sub(session_maker, "blazej", EP1)
    now = datetime.now(UTC)

    await push.check_silent_and_ended(now)  # nigdy się nie odezwał: świeżo zamontowany
    async with session_maker() as s:
        sensor = await s.get(Sensor, SENSOR_ID)
        sensor.last_seen = now - timedelta(hours=13)
        sensor.active = False
        await s.commit()
    await push.check_silent_and_ended(now)
    assert sent.calls == []

    async with session_maker() as s:
        (await s.get(Sensor, SENSOR_ID)).active = True
        await s.commit()
    await add_release(session_maker, now - timedelta(hours=1), now + timedelta(hours=1))
    await push.check_silent_and_ended(now)  # trwa wydanie
    assert sent.calls == []
    async with session_maker() as s:
        assert (await s.get(Sensor, SENSOR_ID)).silent_notified is False


async def test_koniec_wydania_push_raz(sent, session_maker, make_user, ranges):
    await make_user("blazej", range_id=ranges[0])
    await add_sub(session_maker, "blazej", EP1)
    now = datetime.now(UTC)
    await set_last_seen(session_maker, now - timedelta(minutes=10))
    release_id = await add_release(
        session_maker, now - timedelta(hours=4), now - timedelta(minutes=5)
    )
    await add_release(session_maker, now - timedelta(hours=2), now + timedelta(hours=2))
    await push.check_silent_and_ended(now)  # zaraz po nim trwa następne: nic
    assert sent.calls == []

    async with session_maker() as s:
        await s.execute(delete(Release).where(Release.ends_at > now))
        (await s.get(Release, release_id)).end_notified = False
        await s.commit()
    await push.check_silent_and_ended(now)
    await push.check_silent_and_ended(now)
    assert [p for _, p in sent.calls] == [
        {
            "type": "release_ended",
            "sensor_id": SENSOR_ID,
            "release_id": release_id,
            "title": "Koniec wydania: Skład przy drodze 5",
            "body": "Wyciszenie się skończyło, czujnik znów pilnuje mygły",
            "url": "/releases",
        }
    ]


async def test_stare_i_recznie_zakonczone_wydanie_bez_pusha(
    client, forester, sent, session_maker
):
    await add_sub(session_maker, "blazej", EP1)
    now = datetime.now(UTC)
    old_id = await add_release(
        session_maker, now - timedelta(hours=8), now - timedelta(hours=3)
    )
    ended_id = await add_release(
        session_maker, now - timedelta(hours=1), now + timedelta(hours=3)
    )
    r = await client.post(f"/api/v1/releases/{ended_id}/end", headers=forester)
    assert r.status_code == 200

    await push.check_silent_and_ended(datetime.now(UTC))
    assert sent.calls == []
    async with session_maker() as s:
        assert (await s.get(Release, old_id)).end_notified is True
