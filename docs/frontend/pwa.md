# PWA

Aplikację można zainstalować na Androidzie jak zwykłą aplikację: ikona na ekranie głównym, otwiera się bez paska przeglądarki. iOS i instalacja na komputerze nie są wspierane.

## Aktualizacje

Zainstalowana aplikacja aktualizuje się sama (`registerType: 'autoUpdate'`, rejestracja w `src/main.tsx`):

1. Aplikacja sprawdza, czy na serwerze jest nowa wersja: przy każdym wczytaniu, **przy powrocie z tła** i co godzinę, gdy jest otwarta (`src/lib/pwa-update.ts`). Bez internetu nie sprawdza, działa zapisana wersja.
2. Nowa wersja pobiera się w tle, a po pobraniu **strona sama się przeładowuje**.

Samo zachowanie przeglądarki nie wystarcza: sprawdza ona nowy service worker tylko przy wczytaniu strony, a aplikacja na Androidzie zwykle wraca z tła bez wczytywania. Dlatego wcześniej nowa wersja pojawiała się dopiero po wejściu przez adres URL.

Przeładowanie może przerwać wypełnianie formularza (np. zakładanie konta). Zdarza się to tylko przy pierwszym powrocie do aplikacji po wdrożeniu. Docelowo zamiast tego będzie pasek „Jest nowa wersja – Odśwież”.

Zmiana ikony lub nazwy dociera wolniej, Chrome sprawdza manifest mniej więcej raz dziennie.

### Test aktualizacji

1. Zbuduj i zainstaluj aplikację (USB albo localtunnel, niżej) i zostaw ją w tle.
2. Zmień coś widocznego, np. tekst w `src/locales/pl.json`, i uruchom ponownie `npm run build` oraz `npm run preview -- --host 127.0.0.1`.
3. Wróć do aplikacji z listy ostatnich: po chwili powinna sama się przeładować i pokazać zmianę.

## Test na telefonie

Instalacja wymaga HTTPS albo `localhost`. Przez zwykłe Wi‑Fi (`http://<IP laptopa>:4173`) Chrome nie uruchomi service workera, więc zamiast aplikacji powstanie tylko skrót otwierający się w przeglądarce. Są dwa sposoby:

- **przez localtunnel:** publiczny adres HTTPS, bez kabla i bez debugowania.


## Test przez localtunnel

[localtunnel](https://github.com/localtunnel/localtunnel) daje tymczasowy adres `https://…loca.lt` prowadzący do `preview` na laptopie. Telefon może być w dowolnej sieci.

1. Laptop, pierwszy terminal:
   ```bash
   cd frontend
   npm run build
   npm run preview -- --host 127.0.0.1
   ```
2. Drugi terminal:
   ```bash
   npx localtunnel --port 4173 --local-host 127.0.0.1
   ```
   Wypisze adres, np. `your url is: https://ciche-drzewo-12.loca.lt`.
3. Przy pierwszym wejściu localtunnel prosi o **Tunnel Password**: to publiczne IP laptopa, widoczne na laptopie pod `https://loca.lt/mytunnelpassword`.
4. W Chrome na telefonie wejdź na adres z kroku 2, wpisz hasło i stuknij **„Zainstaluj aplikację”**.