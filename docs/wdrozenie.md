# Wdrożenie na serwer (Mikrus)

Serwer: [Mikrus](https://mikr.us/) 2.1 (1 GB RAM bez swapu, 10 GB dysku, kontener LXC z Dockerem). Obrazy buduje GitHub Actions ([obrazy.yml](../.github/workflows/obrazy.yml)), serwer je tylko pobiera z GHCR. Pliki serwera: [deploy/](../deploy).

## Układ

```
LoPy ──HTTP──► srvNN.mikr.us:PORT ─┐
TTN  ──HTTPS─► srvNN-PORT.wykr.es ─┤  (HTTPS robi Mikrus)
PWA  ──HTTPS─► srvNN-PORT.wykr.es ─┤
                                   ▼
                     caddy :80 (detektor-web: zbudowany frontend + Caddy)
                     ├─ /api/*, /health, /docs  →  web:8000 (detektor-api, uvicorn, 1 worker)
                     └─ reszta                  →  aplikacja (SPA)
                                                    web → db (TimescaleDB, bez portu na zewnątrz)
```

`PORT` to port z puli Mikrusa (`20000+ID` albo `30000+ID`). Na zewnątrz jest tylko `caddy`.

| Serwis | Obraz | Limit RAM | Zużycie w spoczynku (test lokalny) |
|---|---|---|---|
| `db` | `timescale/timescaledb:latest-pg17` | 450 MB | ~50 MB |
| `web` | `ghcr.io/kacper-slezak/detektor-api` | 300 MB | ~62 MB |
| `caddy` | `ghcr.io/kacper-slezak/detektor-web` | 64 MB | ~12 MB |

## 0. Przed pierwszym wdrożeniem (raz)

1. Pakiety `detektor-api` i `detektor-web` w GHCR ustawione jako **Public** (GitHub → profil → Packages → pakiet → Package settings → Change visibility). Inaczej serwer potrzebuje `docker login ghcr.io` z tokenem `read:packages`.
2. Na Mikrusie: logowanie po SSH kluczem (port `10000+ID`), `docker run --rm hello-world` działa.
3. Sprawdzenie, czy port działa po HTTP i przez wykr.es (na serwerze `python3 -m http.server PORT`, na laptopie):
   ```bash
   curl -I http://srvNN.mikr.us:PORT/
   ```
   ```bash
   curl -I https://srvNN-PORT.wykr.es/
   ```
   Oba muszą zwrócić `200`. Jeśli wykr.es nie odpowiada, opisz to w issue, zanim pójdziesz dalej.

## 1. Pierwsze wdrożenie

```bash
git clone https://github.com/Kacper-Slezak/Detektor-kradziezy-drewna.git
cd Detektor-kradziezy-drewna/deploy
```

Plik `deploy/.env` (nie trafia do repo). **Nowe** sekrety, nie te z laptopów:

```bash
cat > .env <<EOF
PUBLIC_PORT=20123
TAG=latest
POSTGRES_PASSWORD=$(python3 -c "import secrets; print(secrets.token_hex(24))")
JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(48))")
INGEST_API_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
SEED_ADMIN_PASSWORD=
VAPID_PUBLIC_KEY=
VAPID_PRIVATE_KEY=
VAPID_SUBJECT=mailto:
EOF
chmod 600 .env
```

- `PUBLIC_PORT`: port z panelu Mikrusa.
- `POSTGRES_PASSWORD` jako hex, bo trafia do adresu bazy (`DATABASE_URL`), gdzie znaki typu `@` czy `/` by go zepsuły.
- Pozostałe zmienne: [backend/konfiguracja.md](backend/konfiguracja.md).

Start, tabele i konto admina:

```bash
docker compose -f compose.prod.yml pull
docker compose -f compose.prod.yml up -d
docker compose -f compose.prod.yml run --rm web alembic upgrade head
docker compose -f compose.prod.yml run --rm web python -m app.seed      # hasło admina w konsoli, jeśli SEED_ADMIN_PASSWORD puste
```

Pierwsze trzy komendy robi też `./auto-update.sh` (pobranie, migracje, start), tak samo jak potem przy każdej aktualizacji.

`seed --demo` tylko na serwerze do prezentacji: konta demo mają wspólne, znane hasło.

**Gotowe, gdy:**
- `docker compose -f compose.prod.yml ps`: `db` i `web` mają `(healthy)`, `caddy` działa,
- `curl https://srvNN-PORT.wykr.es/health` zwraca `{"status":"ok"}`,
- w przeglądarce `https://srvNN-PORT.wykr.es` pokazuje logowanie, admin się loguje,
- `docker stats --no-stream`: każdy serwis wyraźnie poniżej limitu.

## 2. Urządzenia

- Płytka (bez TLS, [testowanie.md, sekcja 6](testowanie.md#6-płytka-lopy-przez-wi-fi)): `API_URL = "http://srvNN.mikr.us:PORT"`, `INGEST_KEY` = `INGEST_API_KEY` z `deploy/.env` serwera.
- Webhook TTN (gdy powstanie `/ingest/ttn`): `https://srvNN-PORT.wykr.es/api/v1/ingest/ttn`.
- Telefony: aplikacja z `https://srvNN-PORT.wykr.es`, „Zainstaluj aplikację” w Chrome.

## 3. Aktualizacja (automatyczna)

Po merge'u do `main` GitHub Actions buduje nowe obrazy (zakładka **Actions** → „Obrazy”, ok. 3–5 min), a serwer sam je wdraża: [deploy/auto-update.sh](../deploy/auto-update.sh) uruchamiany z crona co 5 min. Od merge'a do nowej wersji na serwerze mija zwykle 8–10 min.

Cron (`crontab -e`, raz, po pierwszym wdrożeniu):

```
*/5 * * * * $HOME/Detektor-kradziezy-drewna/deploy/auto-update.sh >> $HOME/deploy.log 2>&1
```

Co robi skrypt przy każdym uruchomieniu:

1. `git pull` plików `deploy/` z `main` i `docker compose pull` obrazów `web` i `caddy`.
2. Gdy nic się nie zmieniło: koniec, bez wpisu w logu.
3. Gdy jest nowa wersja: działającą wersję taguje jako `:previous`, robi **backup**, uruchamia **migracje nowym obrazem** (stare kontenery dalej działają), podmienia kontenery i czeka do 90 s na `/health`.
4. Gdy `/health` nie odpowiada: wraca do `:previous` i zapisuje tę wersję w `deploy/.auto-update-failed`, żeby nie próbować jej co 5 minut. Następna nowa wersja (np. poprawka) wdroży się normalnie. **Migracji nie cofa**: jeśli zepsuta wersja zmieniła bazę, do ręcznej decyzji (`alembic downgrade` albo backup sprzed wdrożenia, sekcja 4).
5. Gdy migracje się nie udadzą: nic nie podmienia, zostaje poprzednia wersja.

Dwa uruchomienia naraz nie są możliwe (`flock`). Obraz bazy (`timescaledb`) automat pomija: jego aktualizacja to ręczny `docker compose -f compose.prod.yml pull db && docker compose -f compose.prod.yml up -d db`.

Log:

```bash
tail -n 30 ~/deploy.log
```

```
2026-11-09T19:21:24+01:00 nowa wersja: web=1992f086af05 caddy=2da49f6df0e4
2026-11-09T19:21:24+01:00 OK /root/backups/detektor-20261109-192124.dump 32K
2026-11-09T19:21:34+01:00 OK: wdrożone (web=1992f086af05 caddy=2da49f6df0e4 )
```

**Nie edytuj plików repo na serwerze** (poza `deploy/.env`): `git pull --ff-only` odmówi wtedy aktualizacji i automat będzie co 5 min kończył się błędem w logu.

**Zatrzymanie na konkretnej wersji:** każdy obraz ma też tag `sha-<7 znaków commita>`. W `.env` ustaw `TAG=sha-abc1234` i uruchom `./auto-update.sh` (albo poczekaj na cron). Automat zostaje przy tej wersji, dopóki `TAG` nie wróci do `latest`. Migracji nie cofa: jeśli nowsza wersja zmieniła bazę, najpierw `alembic downgrade` o tyle kroków, ile dodała.

**Ręcznie, bez czekania na cron:**

```bash
~/Detektor-kradziezy-drewna/deploy/auto-update.sh
```

## 4. Kopie zapasowe

[deploy/backup.sh](../deploy/backup.sh): `pg_dump` do `~/backups`, zostaje 7 najnowszych. Cron (`crontab -e`):

```
30 3 * * * $HOME/Detektor-kradziezy-drewna/deploy/backup.sh >> $HOME/backups/backup.log 2>&1
```

Kopie na tym samym serwerze nie chronią przed jego utratą, dlatego raz w tygodniu ściągnij je na laptop:

```bash
scp -P 10123 'root@srvNN.mikr.us:backups/*.dump' ./backups-mikrus/
```

**Odtworzenie** (sprawdzone na kopii: te same liczby wierszy i hypertable `messages`). Baza musi być pusta, TimescaleDB wymaga `pre_restore`/`post_restore`:

```bash
C="docker compose -f compose.prod.yml"
$C stop web
$C exec -T db psql -U detektor -d postgres -c "DROP DATABASE detektor" -c "CREATE DATABASE detektor"
$C exec -T db psql -U detektor -d detektor -c "CREATE EXTENSION IF NOT EXISTS timescaledb" -c "SELECT timescaledb_pre_restore()"
$C exec -T db pg_restore -U detektor -d detektor --no-owner < ~/backups/detektor-RRRRMMDD-GGMMSS.dump
$C exec -T db psql -U detektor -d detektor -c "SELECT timescaledb_post_restore()"
$C start web
```

Raz na jakiś czas warto odtworzyć kopię na laptopie (te same komendy w lokalnym `backend/`): kopia, której nikt nie odtworzył, to tylko nadzieja.

## 5. Co dzieje się samo

| Co | Gdzie |
|---|---|
| restart po awarii lub restarcie serwera | `restart: unless-stopped` |
| `web` zdrowy tylko z działającą bazą | `/health` robi `SELECT 1`, przy błędzie `503` |
| usuwanie surowych ramek starszych niż 90 dni | polityka retencji TimescaleDB na `messages` (migracja `a3c9e1f20b47`), raz dziennie; alarmy, wydania i stan czujników zostają |
| limit zgadywania haseł | 5 nieudanych logowań na login w 15 min, potem `429` ([api.md](backend/api.md#1-logowanie-i-hasło)) |

Monitoring z zewnątrz: darmowy [UptimeRobot](https://uptimerobot.com/) (HTTP(s), co 5 min) na `https://srvNN-PORT.wykr.es/health`, z mailem przy awarii.

## 6. Typowe problemy

| Objaw | Przyczyna | Rozwiązanie |
|---|---|---|
| `pull`: `denied` / `unauthorized` | pakiet w GHCR prywatny | sekcja 0, punkt 1 |
| `PUBLIC_PORT` / `POSTGRES_PASSWORD`: `required variable is missing` | brak w `deploy/.env` | uzupełnić `.env` |
| `web` ciągle `unhealthy`, w logach `password authentication failed` | zmienione `POSTGRES_PASSWORD` po pierwszym starcie bazy | przywrócić stare hasło; nowe hasło działa tylko z nową bazą (`down -v` kasuje dane) |
| serwis znika i wraca, `docker inspect` pokazuje `OOMKilled: true` | przekroczony `mem_limit` | `docker stats`; podnieść limit w `compose.prod.yml` albo plan Mikrusa 3.0 |
| `relation "…" does not exist` | brak migracji | `run --rm web alembic upgrade head` |
| aplikacja pokazuje starą wersję | obraz jeszcze się buduje, automat nie zdążył albo wersja nie wstała | Actions → „Obrazy”; `tail ~/deploy.log`; `cat deploy/.auto-update-failed`; w aplikacji powrót z tła przeładowuje ją ([pwa.md](frontend/pwa.md)) |
| logi | – | `docker compose -f compose.prod.yml logs -f --tail 100 web` |
