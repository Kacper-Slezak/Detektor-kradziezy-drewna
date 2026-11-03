"""Pomocnicze funkcje do testów (logowanie). Fixture'y są w conftest.py."""

PASSWORD = "Haslo-testowe-1"


async def login(client, login="blazej", password=PASSWORD):
    return await client.post("/api/v1/auth/login", json={"login": login, "password": password})


async def auth(client, user_login="blazej", password=PASSWORD) -> dict:
    """Nagłówek Authorization po zalogowaniu."""
    r = await login(client, user_login, password)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}
