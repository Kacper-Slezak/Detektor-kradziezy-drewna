# PWA

Aplikację można zainstalować na Androidzie jak zwykłą aplikację: ikona na ekranie głównym, otwiera się bez paska przeglądarki. iOS i instalacja na komputerze nie są wspierane.

## Aktualizacje

Zainstalowana aplikacja aktualizuje się sama (`registerType: 'autoUpdate'`). Po wdrożeniu nowej wersji przy najbliższym otwarciu pobiera nowe pliki w tle i się przeładowuje. Zmiana ikony lub nazwy dociera wolniej, Chrome sprawdza manifest mniej więcej raz dziennie.

## Test na telefonie

Instalacja wymaga HTTPS albo `localhost`. Przez zwykłe Wi‑Fi (`http://<IP laptopa>:4173`) Chrome nie uruchomi service workera, więc zamiast aplikacji powstanie tylko skrót otwierający się w przeglądarce. Są dwa sposoby:

- **przez USB:** telefon widzi aplikację jako `localhost`, potrzebne debugowanie USB,
- **przez localtunnel:** publiczny adres HTTPS, bez kabla i bez debugowania.

## Test przez USB

Przez USB telefon widzi aplikację jako `localhost`, więc HTTPS nie jest potrzebne.

### 1. Telefon (jednorazowo)

1. Włącz opcje programisty: **Ustawienia → O telefonie → 7× „Numer wersji”** (Samsung: *Informacje o oprogramowaniu → Numer wersji*, Xiaomi/POCO: *Wersja OS*).
2. W **Opcjach programisty** włącz **Debugowanie USB**.
3. Podłącz telefon kablem i zatwierdź **„Zezwolić na debugowanie USB?”**.

### 2. Laptop

```bash
cd frontend
npm run build
npm run preview -- --host 127.0.0.1
```


### 3. Przekierowanie portu

- **Chrome:** `chrome://inspect/#devices` → **Port forwarding** → `4173` → `127.0.0.1:4173`, zaznacz *Enable port forwarding*.

Przekierowanie znika po odłączeniu kabla.

### 4. Instalacja

W Chrome na telefonie (nie Samsung Internet) wejdź na `localhost:4173` i stuknij **„Zainstaluj aplikację”**.


## Test przez localtunnel (bez USB)

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