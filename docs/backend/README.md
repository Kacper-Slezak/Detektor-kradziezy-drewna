# Dokumentacja backendu

| Dokument | Zawartość |
|---|---|
| [docker.md](docker.md) | Środowisko Docker Compose: serwisy, wolumeny, typowe komendy, problemy |
| [konfiguracja.md](konfiguracja.md) | Zmienne środowiskowe i `DATABASE_URL` (Docker vs lokalnie) |
| [model-danych.md](model-danych.md) | Tabele, relacje, hypertable `messages` i migracje Alembic |
| [boot-id.md](boot-id.md) | Ochrona przed powtórkami: ramka wersji 3 (`boot_id` w nagłówku), wersje 1–2 przejściowo (`LEGACY_FRAMES`), reset |
| [szyfrowanie.md](szyfrowanie.md) | Szyfrowanie ramek AES-128 (`FRAME_AES_KEY`), odszyfrowanie w `/ingest` |

Szybki start: [backend/README.md](../../backend/README.md).

> Nowe dokumenty backendu (endpointy, model danych, migracje Alembic) dodawaj w tym katalogu i dopisuj do tabeli powyżej.
