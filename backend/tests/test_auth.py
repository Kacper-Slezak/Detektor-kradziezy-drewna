from datetime import UTC, datetime, timedelta

import jwt
import pytest
from sqlalchemy import select

from app.config import settings
from app.models import Range, User
from app.security import ALGORITHM, create_token, hash_password
from app.seed import create_admin

PASSWORD = "Haslo-testowe-1"


@pytest.fixture
async def make_user(session_maker):
    """Tworzy użytkownika w bazie i zwraca jego id."""

    async def _make(login="blazej", role="forester", range_id=None, **kwargs) -> int:
        kwargs.setdefault("must_change_password", False)
        async with session_maker() as s:
            user = User(
                login=login,
                password_hash=await hash_password(PASSWORD),
                full_name=f"Imię {login}",
                role=role,
                range_id=range_id,
                **kwargs,
            )
            s.add(user)
            await s.commit()
            return user.id

    return _make


@pytest.fixture
async def range_id(session_maker) -> int:
    async with session_maker() as s:
        r = Range(name="Leśnictwo Dąbrowa")
        s.add(r)
        await s.commit()
        return r.id


async def login(client, login="blazej", password=PASSWORD):
    return await client.post("/api/v1/auth/login", json={"login": login, "password": password})


async def auth(client, user_login="blazej", password=PASSWORD) -> dict:
    """Nagłówek Authorization po zalogowaniu."""
    r = await login(client, user_login, password)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture
async def admin(client, make_user):
    await make_user("admin", role="admin")
    return await auth(client, "admin")


# --- logowanie ---


async def test_logowanie_ok(client, make_user, range_id):
    await make_user(range_id=range_id)
    r = await login(client)

    assert r.status_code == 200
    body = r.json()
    assert body["token"]
    expires = datetime.fromisoformat(body["expires_at"])
    assert timedelta(hours=23, minutes=55) < expires - datetime.now(UTC) <= timedelta(hours=24)
    assert body["user"] == {
        "id": 1,
        "login": "blazej",
        "full_name": "Imię blazej",
        "role": "forester",
        "range": {"id": range_id, "name": "Leśnictwo Dąbrowa"},
        "must_change_password": False,
    }
    assert "password_hash" not in str(body)


async def test_zle_haslo_401(client, make_user):
    await make_user()
    r = await login(client, password="zle-haslo")
    assert r.status_code == 401


async def test_nieistniejacy_login_401(client):
    r = await login(client, login="nikt")
    assert r.status_code == 401


async def test_nieaktywne_konto_401(client, make_user):
    await make_user(active=False)
    r = await login(client)
    assert r.status_code == 401


async def test_haslo_nie_jest_zapisane_jawnie(client, make_user, session_maker):
    await make_user()
    async with session_maker() as s:
        stored = await s.scalar(select(User.password_hash))
    assert PASSWORD not in stored
    assert stored.startswith("$argon2")


# --- tokeny: 401 ---


async def test_me_bez_tokena_401(client):
    r = await client.get("/api/v1/auth/me")
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"


async def test_me_ze_zlym_tokenem_401(client):
    r = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer to.nie.jest.token"})
    assert r.status_code == 401


async def test_me_z_wygaslym_tokenem_401(client, make_user):
    user_id = await make_user()
    expired = jwt.encode(
        {"sub": str(user_id), "exp": datetime.now(UTC) - timedelta(minutes=1)},
        settings.jwt_secret,
        algorithm=ALGORITHM,
    )
    r = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {expired}"})
    assert r.status_code == 401


async def test_me_z_tokenem_podpisanym_innym_kluczem_401(client, make_user):
    user_id = await make_user()
    forged = jwt.encode(
        {"sub": str(user_id), "exp": datetime.now(UTC) + timedelta(hours=1)},
        "inny-klucz-ale-wystarczajaco-dlugi-123",
        algorithm=ALGORITHM,
    )
    r = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {forged}"})
    assert r.status_code == 401


async def test_token_dezaktywowanego_konta_przestaje_dzialac(client, make_user, admin):
    forester_id = await make_user()
    forester = await auth(client)
    assert (await client.get("/api/v1/auth/me", headers=forester)).status_code == 200

    r = await client.patch(f"/api/v1/users/{forester_id}", json={"active": False}, headers=admin)
    assert r.status_code == 200
    assert (await client.get("/api/v1/auth/me", headers=forester)).status_code == 401


async def test_me_zwraca_zalogowanego(client, make_user):
    await make_user()
    r = await client.get("/api/v1/auth/me", headers=await auth(client))
    assert r.status_code == 200
    assert r.json()["login"] == "blazej"
    assert r.json()["range"] is None


# --- zmiana hasła ---


async def test_zmiana_hasla(client, make_user):
    await make_user()
    headers = await auth(client)

    r = await client.post(
        "/api/v1/auth/change-password",
        json={"old_password": PASSWORD, "new_password": "MojeNoweHaslo2026"},
        headers=headers,
    )
    assert r.status_code == 204

    assert (await login(client, password=PASSWORD)).status_code == 401
    assert (await login(client, password="MojeNoweHaslo2026")).status_code == 200


async def test_zmiana_hasla_zle_stare_400(client, make_user):
    await make_user()
    r = await client.post(
        "/api/v1/auth/change-password",
        json={"old_password": "zle", "new_password": "MojeNoweHaslo2026"},
        headers=await auth(client),
    )
    assert r.status_code == 400
    assert (await login(client)).status_code == 200  # stare hasło dalej działa


async def test_zmiana_hasla_na_to_samo_400(client, make_user):
    await make_user()
    r = await client.post(
        "/api/v1/auth/change-password",
        json={"old_password": PASSWORD, "new_password": PASSWORD},
        headers=await auth(client),
    )
    assert r.status_code == 400


async def test_zmiana_hasla_za_krotkie_422(client, make_user):
    await make_user()
    r = await client.post(
        "/api/v1/auth/change-password",
        json={"old_password": PASSWORD, "new_password": "krotkie"},
        headers=await auth(client),
    )
    assert r.status_code == 422


async def test_zmiana_hasla_bez_tokena_401(client):
    r = await client.post(
        "/api/v1/auth/change-password", json={"old_password": "a", "new_password": "abcdefgh"}
    )
    assert r.status_code == 401


async def test_wymuszona_zmiana_hasla(client, make_user):
    await make_user("admin", role="admin", must_change_password=True)
    r = await login(client, "admin")
    assert r.status_code == 200
    assert r.json()["user"]["must_change_password"] is True
    headers = {"Authorization": f"Bearer {r.json()['token']}"}

    # do czasu zmiany hasła: /auth/me działa, reszta API jest zablokowana
    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 200
    blocked = await client.get("/api/v1/users", headers=headers)
    assert blocked.status_code == 403
    assert "hasło" in blocked.json()["detail"]

    r = await client.post(
        "/api/v1/auth/change-password",
        json={"old_password": PASSWORD, "new_password": "MojeNoweHaslo2026"},
        headers=headers,
    )
    assert r.status_code == 204

    # ten sam token działa już na całe API
    assert (await client.get("/api/v1/users", headers=headers)).status_code == 200
    me = await client.get("/api/v1/auth/me", headers=headers)
    assert me.json()["must_change_password"] is False


# --- uprawnienia (403) ---


@pytest.mark.parametrize("role", ["forester", "district_manager"])
async def test_endpointy_admina_zamkniete_dla_innych_rol(client, make_user, range_id, role):
    await make_user("ktos", role=role, range_id=range_id)
    headers = await auth(client, "ktos")

    assert (await client.get("/api/v1/users", headers=headers)).status_code == 403
    assert (await client.get("/api/v1/ranges", headers=headers)).status_code == 403
    assert (await client.patch("/api/v1/users/1", json={"active": False}, headers=headers)).status_code == 403
    assert (await client.post("/api/v1/users/1/reset-password", headers=headers)).status_code == 403
    new_user = {"login": "x", "full_name": "X", "role": "admin", "password": "Haslo-testowe-1"}
    assert (await client.post("/api/v1/users", json=new_user, headers=headers)).status_code == 403


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/v1/users"),
        ("POST", "/api/v1/users"),
        ("PATCH", "/api/v1/users/1"),
        ("POST", "/api/v1/users/1/reset-password"),
        ("GET", "/api/v1/ranges"),
    ],
)
async def test_endpointy_admina_bez_tokena_401(client, method, path):
    r = await client.request(method, path)
    assert r.status_code == 401


# --- zarządzanie użytkownikami ---


async def test_lista_uzytkownikow(client, admin, make_user, range_id):
    await make_user(range_id=range_id)
    r = await client.get("/api/v1/users", headers=admin)

    assert r.status_code == 200
    assert [u["login"] for u in r.json()] == ["admin", "blazej"]
    assert r.json()[1] == {
        "id": 2,
        "login": "blazej",
        "full_name": "Imię blazej",
        "role": "forester",
        "range_id": range_id,
        "active": True,
        "must_change_password": False,
    }


async def test_utworzenie_uzytkownika(client, admin, range_id):
    r = await client.post(
        "/api/v1/users",
        json={
            "login": "nowy.lesniczy",
            "full_name": "Jan Nowy",
            "role": "forester",
            "range_id": range_id,
            "password": "Tymczasowe123!",
        },
        headers=admin,
    )
    assert r.status_code == 201
    assert r.json()["must_change_password"] is True
    assert r.json()["active"] is True
    assert "password" not in r.json() and "password_hash" not in r.json()

    # nowy użytkownik loguje się hasłem od admina i musi je zmienić
    r = await login(client, "nowy.lesniczy", "Tymczasowe123!")
    assert r.status_code == 200
    assert r.json()["user"]["must_change_password"] is True


async def test_utworzenie_z_zajetym_loginem_409(client, admin, make_user):
    await make_user("blazej")
    r = await client.post(
        "/api/v1/users",
        json={"login": "blazej", "full_name": "X", "role": "admin", "password": "Tymczasowe123!"},
        headers=admin,
    )
    assert r.status_code == 409


async def test_lesniczy_bez_lesnictwa_400(client, admin):
    r = await client.post(
        "/api/v1/users",
        json={"login": "x", "full_name": "X", "role": "forester", "password": "Tymczasowe123!"},
        headers=admin,
    )
    assert r.status_code == 400


async def test_nieistniejace_lesnictwo_400(client, admin):
    r = await client.post(
        "/api/v1/users",
        json={
            "login": "x",
            "full_name": "X",
            "role": "forester",
            "range_id": 999,
            "password": "Tymczasowe123!",
        },
        headers=admin,
    )
    assert r.status_code == 400


async def test_nieznana_rola_422(client, admin):
    r = await client.post(
        "/api/v1/users",
        json={"login": "x", "full_name": "X", "role": "szef", "password": "Tymczasowe123!"},
        headers=admin,
    )
    assert r.status_code == 422


async def test_dezaktywacja_blokuje_logowanie(client, admin, make_user):
    user_id = await make_user()
    r = await client.patch(f"/api/v1/users/{user_id}", json={"active": False}, headers=admin)
    assert r.status_code == 200 and r.json()["active"] is False
    assert (await login(client)).status_code == 401


async def test_zmiana_roli_i_lesnictwa(client, admin, make_user, range_id):
    user_id = await make_user(range_id=range_id)
    r = await client.patch(
        f"/api/v1/users/{user_id}", json={"role": "district_manager", "range_id": None}, headers=admin
    )
    assert r.status_code == 200
    assert r.json()["role"] == "district_manager"
    assert r.json()["range_id"] is None


async def test_patch_nie_zrobi_lesniczego_bez_lesnictwa(client, admin, make_user):
    user_id = await make_user("szef", role="district_manager")
    r = await client.patch(f"/api/v1/users/{user_id}", json={"role": "forester"}, headers=admin)
    assert r.status_code == 400


async def test_patch_pomija_pola_ktorych_nie_podano(client, admin, make_user, range_id):
    user_id = await make_user(range_id=range_id)
    r = await client.patch(f"/api/v1/users/{user_id}", json={"full_name": "Nowe Imię"}, headers=admin)
    assert r.status_code == 200
    assert r.json()["full_name"] == "Nowe Imię"
    assert r.json()["range_id"] == range_id and r.json()["role"] == "forester"


async def test_admin_nie_dezaktywuje_ani_nie_degraduje_siebie(client, admin):
    r = await client.patch("/api/v1/users/1", json={"active": False}, headers=admin)
    assert r.status_code == 409
    r = await client.patch("/api/v1/users/1", json={"role": "forester", "range_id": None}, headers=admin)
    assert r.status_code == 409
    # zmiana nazwy własnego konta jest w porządku
    r = await client.patch("/api/v1/users/1", json={"full_name": "Szef"}, headers=admin)
    assert r.status_code == 200


async def test_patch_nieistniejacego_404(client, admin):
    r = await client.patch("/api/v1/users/999", json={"active": False}, headers=admin)
    assert r.status_code == 404


async def test_reset_hasla_przez_admina(client, admin, make_user):
    user_id = await make_user()
    r = await client.post(f"/api/v1/users/{user_id}/reset-password", headers=admin)

    assert r.status_code == 200
    temporary = r.json()["temporary_password"]
    assert len(temporary) >= 8

    assert (await login(client, password=PASSWORD)).status_code == 401  # stare hasło nie działa
    r = await login(client, password=temporary)
    assert r.status_code == 200
    assert r.json()["user"]["must_change_password"] is True


async def test_reset_hasla_daje_rozne_hasla(client, admin, make_user):
    user_id = await make_user()
    first = (await client.post(f"/api/v1/users/{user_id}/reset-password", headers=admin)).json()
    second = (await client.post(f"/api/v1/users/{user_id}/reset-password", headers=admin)).json()
    assert first["temporary_password"] != second["temporary_password"]


async def test_reset_hasla_nieistniejacego_404(client, admin):
    r = await client.post("/api/v1/users/999/reset-password", headers=admin)
    assert r.status_code == 404


async def test_lista_lesnictw(client, admin, session_maker):
    async with session_maker() as s:
        s.add_all([Range(name="Leśnictwo Dąbrowa"), Range(name="Leśnictwo Olszyny")])
        await s.commit()
    r = await client.get("/api/v1/ranges", headers=admin)
    assert r.status_code == 200
    assert r.json() == [
        {"id": 1, "name": "Leśnictwo Dąbrowa"},
        {"id": 2, "name": "Leśnictwo Olszyny"},
    ]


# --- seed ---


async def test_seed_tworzy_admina_z_losowym_haslem(session_maker, monkeypatch):
    monkeypatch.setattr(settings, "seed_admin_password", "")
    async with session_maker() as s:
        created, password = await create_admin(s)
    assert created and password

    async with session_maker() as s:
        admin = await s.scalar(select(User).where(User.login == "admin"))
    assert admin.role == "admin" and admin.must_change_password is True


async def test_seed_z_haslem_z_ustawien_i_bez_duplikatow(session_maker, monkeypatch):
    monkeypatch.setattr(settings, "seed_admin_password", "Z-ustawien-123")
    async with session_maker() as s:
        assert await create_admin(s) == (True, None)
    async with session_maker() as s:
        assert await create_admin(s) == (False, None)  # drugi raz nic nie robi


async def test_zalogowanie_na_konto_z_seeda(client, session_maker, monkeypatch):
    monkeypatch.setattr(settings, "seed_admin_password", "Z-ustawien-123")
    async with session_maker() as s:
        await create_admin(s)
    r = await login(client, "admin", "Z-ustawien-123")
    assert r.status_code == 200
    assert r.json()["user"]["role"] == "admin"


# --- konfiguracja i Swagger ---


def test_swagger_ma_przycisk_authorize():
    from app.main import app

    schemes = app.openapi()["components"]["securitySchemes"]
    assert schemes["HTTPBearer"]["scheme"] == "bearer"


def test_brak_jwt_secret_to_blad(monkeypatch):
    monkeypatch.setattr(settings, "jwt_secret", "")
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        create_token(1)
