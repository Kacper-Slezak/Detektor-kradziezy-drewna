"""Raporty nadleśniczego: podsumowanie okresu i eksport CSV (api.md, sekcja 5)."""

import csv
import io
from datetime import UTC, datetime, timedelta

import pytest

from app.models import Alarm, Range, Release, Sensor
from tests.conftest import SENSOR_ID
from tests.utils import auth

S1, S2, S3 = "70B3D57ED0000001", "70B3D57ED0000002", "70B3D57ED0000003"
PERIOD = {"from": "2026-11-02", "to": "2026-11-15"}  # tygodnie ISO 2026-W45 i W46


def utc(*args) -> datetime:
    return datetime(*args, tzinfo=UTC)


@pytest.fixture
async def data(session_maker):
    """4 alarmy i 2 wydania w okresie oraz po 2 tuż poza nim (granice dni)."""
    now = datetime.now(UTC)
    async with session_maker() as s:
        dabrowa = Range(name="Leśnictwo Dąbrowa")
        s.add(dabrowa)
        await s.flush()
        s.add_all(
            [
                Sensor(
                    id=S1,
                    name="Skład 5",
                    range_id=dabrowa.id,
                    lat=50.0,
                    lon=20.0,
                    battery_pct=80,
                    last_seen=now,
                ),
                Sensor(
                    id=S2,
                    name="Skład paśnik",
                    range_id=dabrowa.id,
                    lat=50.1,
                    lon=20.1,
                    battery_pct=15,
                    last_seen=now,
                ),
                Sensor(id=S3, range_id=dabrowa.id),  # niezamontowany
            ]
        )
        await s.flush()  # alarmy i wydania odwołują się do czujników (klucz obcy)

        def alarm(sensor, at, status, **kw):
            s.add(
                Alarm(
                    sensor_id=sensor,
                    started_at=at,
                    last_frame_at=at + timedelta(minutes=2),
                    event_type=1,
                    sources=kw.pop("sources", ["microphone", "vibration"]),
                    confidence=kw.pop("confidence", 87),
                    duration_s=40,
                    energy=180,
                    repeats=kw.pop("repeats", 3),
                    status=status,
                    **kw,
                )
            )

        alarm(
            S1,
            utc(2026, 11, 2, 10),
            "theft",
            response_by="blazej",
            response_at=utc(2026, 11, 2, 11),
            response_comment="przewoźnik ładował 5 kłód",
        )
        alarm(
            S1,
            utc(2026, 11, 3, 12),
            "false_alarm",
            sources=["vibration"],
            response_by="blazej",
            response_at=utc(2026, 11, 3, 13),
            response_comment='=HYPERLINK("http://zlosliwe")',
        )
        alarm(S2, utc(2026, 11, 9, 0, 0, 0), "new")  # poniedziałek 00:00, początek W46
        alarm(S2, utc(2026, 11, 15, 23, 59, 59), "theft")  # ostatnia sekunda okresu
        alarm(S1, utc(2026, 11, 16, 0, 0, 0), "theft")  # dzień po okresie: poza
        alarm(S1, utc(2026, 11, 1, 23, 59, 59), "false_alarm")  # dzień przed: poza

        s.add_all(
            [
                Release(
                    sensor_id=S1,
                    starts_at=utc(2026, 11, 4, 8),
                    ends_at=utc(2026, 11, 4, 12),
                    carrier="TransLas",
                    log_count=40,
                    comment="umowa 12/2026",
                    created_by="blazej",
                ),
                Release(
                    sensor_id=S2,
                    starts_at=utc(2026, 11, 15, 23),
                    ends_at=utc(2026, 11, 16, 3),
                    carrier="@cmd",
                ),
                Release(
                    sensor_id=S1,
                    starts_at=utc(2026, 11, 16),
                    ends_at=utc(2026, 11, 16, 4),
                ),  # poza
            ]
        )
        await s.commit()


@pytest.fixture
async def manager(client, make_user):
    await make_user("bogdan", role="district_manager")
    return await auth(client, "bogdan")


async def get(client, headers, path="summary", **params):
    return await client.get(
        f"/api/v1/reports/{path}", headers=headers, params={**PERIOD, **params}
    )


def rows(response) -> list[list[str]]:
    text = response.content.decode("utf-8-sig")
    return list(csv.reader(io.StringIO(text), delimiter=";"))


# --- podsumowanie ---


async def test_podsumowanie_liczby(client, manager, data):
    r = await get(client, manager)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["period"] == {"from": "2026-11-02", "to": "2026-11-15"}
    assert body["alarms"] == {"total": 4, "theft": 2, "false_alarm": 1, "unanswered": 1}
    assert body["releases"] == 2
    # zamontowane: czujnik z conftest, S1, S2. Cichy tylko czujnik z conftest (nic nie wysłał),
    # S2 ma otwarty alarm (stan alarm), niski stan baterii ma S2 (15%)
    assert body["sensors"] == {"total": 3, "silent": 1, "low_battery": 1}


async def test_podsumowanie_per_czujnik(client, manager, data):
    body = (await get(client, manager)).json()
    assert body["per_sensor"] == [
        {
            "sensor_id": S1,
            "name": "Skład 5",
            "alarms": 2,
            "theft": 1,
            "false_alarm": 1,
            "releases": 1,
        },
        {
            "sensor_id": S2,
            "name": "Skład paśnik",
            "alarms": 2,
            "theft": 1,
            "false_alarm": 0,
            "releases": 1,
        },
        {
            "sensor_id": SENSOR_ID,
            "name": "Skład przy drodze 5",
            "alarms": 0,
            "theft": 0,
            "false_alarm": 0,
            "releases": 0,
        },
    ]  # od najwięcej alarmów, niezamontowany S3 bez danych pominięty


async def test_podsumowanie_per_tydzien(client, manager, data):
    body = (await get(client, manager)).json()
    assert body["per_week"] == [
        {"week": "2026-W45", "alarms": 2, "theft": 1},
        {"week": "2026-W46", "alarms": 2, "theft": 1},
    ]


async def test_granice_okresu_to_dni_utc_wlacznie(client, manager, data):
    # jeden dzień: tylko 2026-11-15 (alarm 23:59:59 i wydanie 23:00)
    body = (
        await get(client, manager, **{"from": "2026-11-15", "to": "2026-11-15"})
    ).json()
    assert body["alarms"]["total"] == 1 and body["releases"] == 1
    assert body["per_week"] == [{"week": "2026-W46", "alarms": 1, "theft": 1}]
    # następny dzień zaczyna się o 00:00 i łapie alarm oraz wydanie z 2026-11-16
    body = (
        await get(client, manager, **{"from": "2026-11-16", "to": "2026-11-16"})
    ).json()
    assert body["alarms"]["total"] == 1 and body["releases"] == 1


async def test_pusty_okres_ma_zera_i_wszystkie_tygodnie(client, manager, data):
    r = await get(client, manager, **{"from": "2026-12-28", "to": "2027-01-10"})
    body = r.json()
    assert body["alarms"] == {"total": 0, "theft": 0, "false_alarm": 0, "unanswered": 0}
    assert body["releases"] == 0
    # tydzień ISO przechodzi przez Nowy Rok: 28.12.2026 (pn) to 2026-W53, 4.01.2027 (pn) to 2027-W01
    assert [w["week"] for w in body["per_week"]] == ["2026-W53", "2027-W01"]
    assert all(w["alarms"] == 0 for w in body["per_week"])


# --- uprawnienia i walidacja ---


@pytest.mark.parametrize("path", ["summary", "export.csv"])
async def test_kto_ma_dostep(client, make_user, data, manager, path):
    assert (await get(client, manager, path)).status_code == 200
    await make_user("admin", role="admin")
    assert (await get(client, await auth(client, "admin"), path)).status_code == 200
    await make_user("blazej", range_id=1)
    assert (await get(client, await auth(client, "blazej"), path)).status_code == 403
    assert (
        await client.get(f"/api/v1/reports/{path}", params=PERIOD)
    ).status_code == 401


@pytest.mark.parametrize("path", ["summary", "export.csv"])
@pytest.mark.parametrize(
    "params",
    [
        {"to": "2026-11-15"},  # brak from
        {"from": "2026-11-02"},  # brak to
        {"from": "2026-11-15", "to": "2026-11-02"},  # to przed from
        {"from": "2026-13-01", "to": "2026-11-15"},  # zła data
    ],
)
async def test_zly_okres_422(client, manager, path, params):
    r = await client.get(f"/api/v1/reports/{path}", headers=manager, params=params)
    assert r.status_code == 422


async def test_limit_dlugosci_okresu(client, manager):
    ok = await client.get(
        "/api/v1/reports/summary",
        headers=manager,
        params={"from": "2026-01-01", "to": "2026-12-31"},
    )  # 365 dni
    assert ok.status_code == 200 and len(ok.json()["per_week"]) >= 52
    too_long = await client.get(
        "/api/v1/reports/summary",
        headers=manager,
        params={"from": "2025-01-01", "to": "2026-01-02"},
    )  # 367 dni
    assert too_long.status_code == 422
    assert "366" in too_long.json()["detail"]


# --- CSV ---


async def test_csv_naglowki_http_i_kodowanie(client, manager, data):
    r = await get(client, manager, "export.csv")
    assert r.status_code == 200
    assert r.headers["content-type"] == "text/csv; charset=utf-8"
    assert (
        r.headers["content-disposition"]
        == 'attachment; filename="raport-2026-11-02_2026-11-15.csv"'
    )
    assert r.content.startswith(b"\xef\xbb\xbf")  # BOM: Excel czyta polskie znaki
    assert b"\r\n" in r.content  # separator `;`, wiersze CRLF


async def test_csv_alarmy_i_wydania_od_najstarszego(client, manager, data):
    table = rows(await get(client, manager, "export.csv"))
    header, body = table[0], table[1:]
    assert header[:3] == ["typ", "id", "czujnik_id"] and len(header) == 17
    assert [r[0] for r in body] == [
        "alarm",
        "alarm",
        "wydanie",
        "alarm",
        "wydanie",
        "alarm",
    ]
    assert [r[5] for r in body] == [
        "2026-11-02 10:00:00",
        "2026-11-03 12:00:00",
        "2026-11-04 08:00:00",
        "2026-11-09 00:00:00",
        "2026-11-15 23:00:00",
        "2026-11-15 23:59:59",
    ]


async def test_csv_wiersz_alarmu(client, manager, data):
    first = rows(await get(client, manager, "export.csv"))[1]
    assert first[0] == "alarm" and first[2:5] == [S1, "Skład 5", "Leśnictwo Dąbrowa"]
    assert first[5:8] == ["2026-11-02 10:00:00", "2026-11-02 10:02:00", "kradzież"]
    assert first[8:11] == ["87", "dźwięk, wibracje", "3"]
    assert first[11:14] == [
        "blazej",
        "2026-11-02 11:00:00",
        "przewoźnik ładował 5 kłód",
    ]
    assert first[14:] == ["", "", ""]  # pola wydania puste
    unanswered = rows(await get(client, manager, "export.csv"))[4]
    assert unanswered[7] == "nowy" and unanswered[11:14] == ["", "", ""]


async def test_csv_wiersz_wydania(client, manager, data):
    release = rows(await get(client, manager, "export.csv"))[3]
    assert release[0] == "wydanie" and release[2:5] == [
        S1,
        "Skład 5",
        "Leśnictwo Dąbrowa",
    ]
    assert release[5:8] == ["2026-11-04 08:00:00", "2026-11-04 12:00:00", "zakończone"]
    assert release[8:11] == ["", "", ""]  # pola alarmu puste
    assert release[13:] == ["umowa 12/2026", "TransLas", "40", "blazej"]


async def test_csv_chroni_przed_wstrzykiwaniem_formul(client, manager, data):
    table = rows(await get(client, manager, "export.csv"))
    assert table[2][13] == '\'=HYPERLINK("http://zlosliwe")'  # komentarz leśniczego
    assert table[5][14] == "'@cmd"  # przewoźnik
    # zwykłe teksty bez zmian
    assert table[1][13] == "przewoźnik ładował 5 kłód"


async def test_csv_pusty_okres_ma_tylko_naglowek(client, manager, data):
    table = rows(
        await get(
            client, manager, "export.csv", **{"from": "2025-01-01", "to": "2025-01-31"}
        )
    )
    assert len(table) == 1 and table[0][0] == "typ"
