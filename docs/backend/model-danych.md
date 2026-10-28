# Model danych

Źródło prawdy dla kodu: `backend/app/models.py`. Schemat w bazie tworzą migracje Alembic (`backend/alembic/versions/`), nie `create_all`.

## Tabele

| Tabela | Kolumny | Opis |
|---|---|---|
| `ranges` | `id`, `name` | Leśnictwo. Leśniczy i czujniki są przypisane do jednego. |
| `users` | `id`, `login` (unikalny), `password_hash`, `full_name`, `role`, `range_id`, `active`, `must_change_password` | Konto. `role`: `forester` / `district_manager` / `admin`. `range_id` jest pusty dla kont bez leśnictwa. |
| `push_subscriptions` | `id`, `fcm_token` (unikalny), `user_id`, `device_label` | Token FCM urządzenia użytkownika do pushy o alarmach. Jeden użytkownik może mieć kilka urządzeń. |
| `sensors` | `id` (DevEUI), `name`, `range_id`, `lat`, `lon`, `active`, `battery_pct`, `last_seen`, `last_counter` | Czujnik = jedno miejsce składowania drewna. |
| `messages` | `id`, `received_at`, `sensor_id`, `msg_type`, `counter`, `payload_hex`, `decoded`, `rssi` | Każda odebrana ramka. **Hypertable TimescaleDB** po `received_at`. |
| `alarms` | `id`, `sensor_id`, `started_at`, `last_frame_at`, `event_type`, `sources`, `confidence`, `duration_s`, `energy`, `repeats`, `status`, `response_by`, `response_at`, `response_comment`, `response_lat`, `response_lon` | Alarm. Powtórzenia ramek ALARM w oknie 10 min są scalane w jeden (`repeats`). `status`: `new` / `theft` / `false_alarm`. Pola `response_*` wypełnia odpowiedź leśniczego; `response_lat`/`response_lon` to pozycja z jego telefonu (dowód obecności, nie jest sprawdzana). |
| `releases` | `id`, `sensor_id`, `starts_at`, `ends_at`, `carrier`, `log_count`, `comment`, `created_by` | Wydanie drewna. W tym oknie czujnik nie generuje alarmów. `created_by` to login leśniczego, który je potwierdził. |

Relacje:

- `sensors.range_id` → `ranges.id`
- `users.range_id` → `ranges.id`
- `push_subscriptions.user_id` → `users.id`
- `messages.sensor_id`, `alarms.sensor_id`, `releases.sensor_id` → `sensors.id`

Typy: czas zawsze z strefą (`timestamptz`, UTC). `decoded`, `sources` to `JSONB`.

## Hypertable `messages`

TimescaleDB wymaga, żeby kolumna czasu była w każdym unikalnym indeksie. Dlatego migracja ustawia klucz główny `messages` na `(id, received_at)` i wywołuje `create_hypertable('messages', 'received_at')`.

W modelu ORM (`Message`) kluczem zostaje `id`. Klucz złożony nie działa z autoincrement w SQLite, którego używają testy.

## Migracje

Wszystkie komendy z katalogu `backend/`. Adres bazy bierze się z `DATABASE_URL`.

```bash
alembic upgrade head                      # zastosuj wszystkie migracje
alembic downgrade base                    # cofnij wszystkie (usuwa dane!)
alembic revision --autogenerate -m "opis" # nowa migracja po zmianie models.py
alembic check                             # czy models.py i baza są zgodne
```

W kontenerze:

```bash
docker compose run --rm web alembic upgrade head
```

Migracje nie uruchamiają się przy starcie aplikacji. Odpalasz je ręcznie po każdej zmianie schematu.
