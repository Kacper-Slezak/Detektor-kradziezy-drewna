# Panel admina

Admin po zalogowaniu od razu trafia do panelu. Leśniczy i nadleśniczy go nie widzą.

## Układ

- **menu boczne** z sekcjami. Gotowa jest sekcja Użytkownicy, a Czujniki i Leśnictwa są wyszarzone z dopiskiem „wkrótce”
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

## Motyw

Jasny, ciemny albo „jak w systemie” (domyślnie), dla całej aplikacji. Przełącznik jest w górnym pasku, a u admina w menu.

- kolory obu motywów są zmiennymi w `src/index.css`, ciemny w stylu Grafany (granatowo‑szary)
- `src/lib/theme.ts` przełącza klasę `dark` na `<html>` i zapamiętuje wybór w `localStorage`
- skrypt w `index.html` ustawia motyw przed załadowaniem aplikacji, więc strona nie miga na biało
