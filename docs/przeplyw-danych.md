# Diagramy przepływu danych (Data Flow Diagrams – DFD)

System detekcji kradzieży drewna (IoT AGH).

---

## 1. DFD Poziom 0 – Diagram kontekstowy

```mermaid
flowchart TD
    subgraph OTOCZENIE["Otoczenie i encje zewnętrzne"]
        E1["Mygła drewna<br/>(Zdarzenia akustyczno-mechaniczne)"]
        E2["Leśniczy / Nadleśniczy<br/>(Smartfon / PWA)"]
        E3["Administrator systemu"]
        E4["Infrastruktura transmisyjna<br/>(Brama LoRaWAN / TTN / Wi-Fi)"]
        E5["Usługa Google FCM<br/>(Push Notifications)"]
    end

    SYS["SYSTEM DETEKTORA KRADZIEŻY DREWNA<br/>(Firmware + Backend FastAPI + Baza TimescaleDB + Frontend PWA)"]

    E1 -->|"Dźwięki piły / załadunku, drgania kłód"| SYS
    SYS -->|"Jednokierunkowe ramki radiowe (LoRa / UDP / HTTP)"| E4
    E4 -->|"Payload HEX + DevEUI + RSSI (/ingest)"| SYS
    SYS -->|"Tokeny FCM i treść alertu"| E5
    E5 -->|"Powiadomienia Push o kradzieży"| E2
    SYS -->|"Stan czujników, pinezki mapy, lista alarmów"| E2
    E2 -->|"Weryfikacja alarmu (GPS z telefonu, status, komentarz), rejestracja wydania"| SYS
    E3 -->|"Zarządzanie czujnikami, leśnictwami i kontami"| SYS
```

---

## 2. DFD Poziom 1 – Diagram procesów systemowych

```mermaid
flowchart TB
    %% Encje zewnętrzne
    subgraph ENCJE["Aktorzy i encje zewnętrzne"]
        E1["Fizyczne czujniki<br/>(Mikrofon OPA344 + MPU-9250)"]
        E2["Leśniczy<br/>(Aplikacja PWA)"]
        E3["Administrator"]
        E4["Sieć transmisyjna<br/>(LoRaWAN / TTN Gateway)"]
        E5["Usługa Push<br/>(Firebase FCM)"]
    end

    %% Magazyny danych
    subgraph MAGAZYNY["Magazyny danych (TimescaleDB / PostgreSQL)"]
        D1[("D1: messages<br/>Hypertable: surowe i zdekodowane ramki")]
        D2[("D2: alarms<br/>Zdarzenia, status, scalenia, odpowiedzi")]
        D3[("D3: sensors<br/>Bateria, licznik, last_seen, GPS")]
        D4[("D4: releases<br/>Okna legalnego wywozu drewna")]
        D5[("D5: users & push_subscriptions<br/>Konta, role RBAC, tokeny FCM")]
    end

    %% Procesy
    subgraph PROCESY["Główne procesy przetwarzania"]
        P1["P1: Akwizycja i Edge AI<br/>(Wybudzenie, analiza audio/drgań, klasyfikacja)"]
        P2["P2: Ingest i Walidacja<br/>(Dekodowanie binarne, kontrola licznika / deduplikacja)"]
        P3["P3: Wyciszanie i Agregacja Alarmów<br/>(Weryfikacja wydań, scalanie w oknie 10 min)"]
        P4["P4: Dyspozycja Powiadomień<br/>(Dobór odbiorców wg range_id, wysyłka FCM)"]
        P5["P5: Prezentacja i Wizualizacja GIS<br/>(Filtracja leśnictw, mapa Leaflet, odświeżanie 60s)"]
        P6["P6: Obsługa Zdarzeń i Wydań<br/>(Odpowiedź leśniczego z pozycją GPS, planowanie wydań)"]
    end

    %% Przepływy
    E1 -->|"Sygnał analogowy audio + I2C ruch"| P1
    P1 -->|"Ramka binarna (BOOT / HEARTBEAT / ALARM)"| E4
    E4 -->|"POST /api/v1/ingest (Hex, DevEUI, RSSI)"| P2

    P2 -->|"Zapis zdekodowanej ramki"| D1
    P2 -->|"Aktualizacja stanu, baterii i licznika"| D3
    D3 -.->|"Odczyt ostatniego licznika"| P2

    P2 -->|"Zdekodowany ALARM"| P3
    D4 -.->|"Sprawdzenie aktywnego wydania drewna"| P3
    P3 -->|"Nowy rekord lub scalenie (repeats++)"| D2

    P3 -->|"Wyzwalacz nowego alarmu"| P4
    D5 -.->|"Pobranie tokenów FCM leśniczych z danego leśnictwa"| P4
    P4 -->|"Wysłanie powiadomienia"| E5
    E5 -->|"Alert na telefon"| E2

    D3 -.->|"Lokalizacje i statusy czujników"| P5
    D2 -.->|"Otwarte alarmy (czerwone pinezki)"| P5
    D5 -.->|"Uprawnienia i przypisane leśnictwo"| P5
    P5 -->|"Strumień stanu mapy (REST / Polling)"| E2

    E2 -->|"POST /alarms/{id}/response (GPS, kradzież/fałszywy)"| P6
    E2 -->|"POST /releases (okno czasowe wywozu)"| P6
    P6 -->|"Aktualizacja statusu alarmu i etykiety dla AI"| D2
    P6 -->|"Wpis wyciszenia czujnika"| D4

    E3 -->|"Rejestracja czujników, przypisanie leśnictwa"| D3
    E3 -->|"Zarządzanie kontami użytkowników"| D5
```

---

## 3. DFD Poziom 2 – Logika procesu odbioru ramki (`/ingest`) i alarmu

```mermaid
flowchart TD
    IN(["Odebranie pakietu: device, payload_hex, received_at, rssi"]) --> P2_1["1. Dekodowanie binarne<br/>(wersja, typ: BOOT/HEARTBEAT/ALARM, counter)"]

    P2_1 -->|"Błąd formatu / złe wartości"| ERR_422["Zwróć HTTP 422<br/>(FrameError)"]
    P2_1 -->|"Poprawna ramka"| P2_2["2. Weryfikacja czujnika w bazie"]

    P2_2 -->|"Brak czujnika w bazie"| ERR_404["Zwróć HTTP 404<br/>(UnknownSensorError)"]
    P2_2 -->|"Czujnik istnieje"| P2_3{"3. Czy duplikat?<br/>(counter <= last_counter mod 65536)"}

    P2_3 -->|"Tak - i nie jest to BOOT"| DUP["Zwróć HTTP 200<br/>status: duplicate<br/>(nic nie zapisuj)"]
    P2_3 -->|"Nie"| P2_4["4. Zapis do bazy:<br/>- Tabela messages (Hypertable)<br/>- Aktualizacja sensors (last_seen, battery, counter)"]

    P2_4 --> P2_5{"5. Jaki typ ramki?"}
    P2_5 -->|"BOOT / HEARTBEAT"| RET_OK["Zwróć HTTP 201<br/>status: stored"]

    P2_5 -->|"ALARM"| P3_1{"6. Czy czujnik wyciszony?<br/>(!active LUB trwa okno w releases)"}
    P3_1 -->|"Tak"| MUTED["Zwróć HTTP 201<br/>status: stored, muted: true<br/>(alarm nie powstaje)"]
    P3_1 -->|"Nie"| P3_2{"7. Czy istnieje otwarty alarm<br/>w oknie 10 min (merge window)?"}

    P3_2 -->|"Tak"| P3_3["Scal z istniejącym:<br/>repeats += 1, max(confidence),<br/>max(duration_s), max(energy),<br/>unia(sources)"]
    P3_2 -->|"Nie"| P3_4["Utwórz nowy rekord w alarms:<br/>status = 'new'"]

    P3_3 --> RET_ALARM["Zwróć HTTP 201<br/>alarm_created: false, alarm_id"]
    P3_4 --> P4_NOTIF["Wyzwalacz PUSH:<br/>Pobierz FCM tokeny leśników z danego range_id<br/>i wyślij powiadomienie"]
    P4_NOTIF --> RET_ALARM_NEW["Zwróć HTTP 201<br/>alarm_created: true, alarm_id"]
```

---

## 4. Tabela strumieni danych

| Identyfikator | Przepływ danych | Typ / Format danych | Zawartość / Pola |
|---|---|---|---|
| **S1** | Sygnał fizyczny $\to$ Urządzenie | Analogowy / I2C | Amplituda i widmo akustyczne (mikrofon), przyspieszenie 3D (MPU-9250). |
| **S2** | Urządzenie $\to$ Sieć $\to$ Backend | Pakiet binarny / JSON | `device` (DevEUI), `payload_hex` (np. `11002A...`), `rssi`, `received_at`. |
| **S3** | Payload $\to$ Dekoder | Struktura bajtowa | Nagłówek (wersja: 4 bity, typ: 4 bity, licznik: 2 B) + ciało specyficzne dla typu. |
| **S4** | Dekoder $\to$ `messages` | Rekord bazy (JSONB) | `sensor_id`, `msg_type`, `counter`, `decoded` (JSON: bateria, confidence, sources, duration, energy). |
| **S5** | Backend $\to$ `sensors` | Relacyjny UPDATE | `battery_pct`, `last_seen`, `last_counter`. |
| **S6** | Ingest $\to$ `alarms` | Relacyjny INSERT/UPDATE | `started_at`, `confidence`, `sources` (`microphone`, `vibration`), `repeats`, `status` (`new`). |
| **S7** | Backend $\to$ Firebase $\to$ Telefon | JSON / Push payload | Tytuł alertu, nazwa składu drewna, leśnictwo, czas, `alarm_id`. |
| **S8** | Backend $\to$ Frontend PWA | JSON (REST API) | Lista czujników (`lat`, `lon`, kolor stanu), lista alarmów. |
| **S9** | Leśniczy $\to$ Backend | JSON (`POST /alarms/{id}/response`) | `result` (`theft` / `false_alarm`), `comment`, `lat`, `lon` (pozycja GPS ze smartfona). |
| **S10** | Leśniczy $\to$ Backend | JSON (`POST /releases`) | `sensor_id`, `starts_at`, `ends_at`, `carrier`, `log_count`, `comment`. |
