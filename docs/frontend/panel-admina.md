# Panel admina

Admin po zalogowaniu od razu trafia do panelu. Leśniczy i nadleśniczy go nie widzą.

## Układ

- **menu boczne** z sekcjami. Gotowe są sekcje Użytkownicy i Czujniki, a Leśnictwa są wyszarzone z dopiskiem „wkrótce”
- na dole menu: zalogowane konto, zmiana hasła, wylogowanie, motyw, język i instalacja aplikacji
- **na telefonie** menu chowa się pod ☰ i zamyka się przyciskiem ✕, kliknięciem obok albo `Esc`

Sekcje przełącza stan w `App.tsx`. Routingu jeszcze nie ma, więc sekcja nie ma własnego adresu.

## Użytkownicy

- kafelki: wszystkie konta, leśniczy, konta z hasłem tymczasowym, nieaktywne
- tabela kont z wyszukiwarką po imieniu, nazwisku i loginie. Status: aktywne, hasło tymczasowe, nieaktywne
- **„+ Dodaj konto”** otwiera panel z prawej:
  - login uzupełnia się z imienia i nazwiska (`Błażej Kowalski` → `blazej.kowalski`) i można go poprawić
  - leśniczy musi mieć leśnictwo, inne role go nie mają
  - hasło tymczasowe admin wpisuje sam albo losuje przyciskiem **„Wylosuj”** (minimum 8 znaków)
- po utworzeniu konta apka **raz** pokazuje login i hasło z przyciskiem „Kopiuj”. Backend zapisuje tylko hash hasła, więc później nie da się go podejrzeć
- przy pierwszym logowaniu nowy użytkownik musi ustawić własne hasło

Endpointy: `GET /users`, `POST /users`, `GET /ranges` ([api.md, sekcja 7](../backend/api.md#7-użytkownicy-admin)). Edycja kont i reset hasła (`PATCH /users/{id}`, `POST /users/{id}/reset-password`) są gotowe na backendzie, ale na froncie jeszcze ich nie ma.

## Czujniki

Czujnik trzeba dodać w panelu, zanim zacznie wysyłać dane. Backend odrzuca ramki od nieznanych urządzeń.

- kafelki: wszystkie czujniki, z alarmem, bez kontaktu, do zamontowania
- tabela z wyszukiwarką po nazwie i ID. Kolumny: nazwa, ID, leśnictwo, leśniczy, stan, bateria (poniżej 20% na czerwono), ostatni kontakt
- stany jak w [api.md](../backend/api.md#stan-czujnika-stan): działa, wyciszony, alarm, bez kontaktu, wyłączony. Czujnik bez lokalizacji front pokazuje jako **niezamontowany**
- **„+ Dodaj czujnik”** otwiera panel z prawej:
  - ID (DevEUI) z naklejki: 16 znaków 0–9 i A–F. Spacje, myślniki i dwukropki są usuwane, litery zamieniane na wielkie
  - leśnictwo jest wymagane, bo bez niego żaden leśniczy nie zobaczy czujnika na liście do montażu
  - nazwa jest opcjonalna, zwykle nadaje ją leśniczy przy montażu
- nowy czujnik jest nieaktywny i bez lokalizacji. Aktywny staje się po montażu przez leśniczego (`PUT /sensors/{id}/mount`)
- **✏️ w wierszu** otwiera edycję: można zmienić leśnictwo i nazwę. ID się nie zmienia, bo pochodzi z urządzenia
- **leśniczego przypisujemy przez leśnictwo.** Czujnik obsługują aktywni leśniczy jego leśnictwa, więc kolumna Leśniczy i listy leśnictw w formularzach („Leśnictwo Dąbrowa · Błażej Kowalski”) wynikają z kont użytkowników. Gdy leśniczy się zmieni, wystarczy przepiąć konto, a czujniki przejdą same

Endpointy `GET /sensors` (wszystkie czujniki), `POST /sensors` z polami `{ "id", "range_id", "name" }` i pole `range_id` w `PATCH /sensors/{id}` są uzgodnione z backendem, ale jeszcze ich nie ma ani w `api.md`, ani w kodzie. Do tego czasu sekcja działa tylko na mocku (`VITE_USE_MOCK=true`), a na prawdziwym backendzie pokazuje błąd 404. Sekcja pobiera też `GET /users`, żeby pokazać leśniczych.

## Motyw

Jasny, ciemny albo „jak w systemie” (domyślnie), dla całej aplikacji. Przełącznik jest w górnym pasku, a u admina w menu.

- kolory obu motywów są zmiennymi w `src/index.css`, ciemny w stylu Grafany (granatowo‑szary)
- `src/lib/theme.ts` przełącza klasę `dark` na `<html>` i zapamiętuje wybór w `localStorage`
- skrypt w `index.html` ustawia motyw przed załadowaniem aplikacji, więc strona nie miga na biało
