# Mapa czujników

Leśniczy i nadleśniczy po zalogowaniu widzą mapę na cały ekran. Admin jej nie ma, bo czujniki przegląda w tabeli w panelu.

## Co widać

- **pinezka = zamontowany czujnik.** Czujnik bez lokalizacji (jeszcze niezamontowany) nie ma pinezki
- kolor pinezki to stan, ten sam co w tabeli admina: 🟢 działa, 🔵 wyciszony, 🔴 alarm, 🟠 bez kontaktu, ⚪ wyłączony
- **alarm** ma większą, pulsującą pinezkę i leży na wierzchu. Przy systemowym „ogranicz animacje” nie pulsuje
- stuknięcie pinezki otwiera dymek z nazwą, ID, stanem („Wyciszony do …”), baterią (poniżej 20% na czerwono) i ostatnim kontaktem
- **legenda** w lewym dolnym rogu liczy czujniki w każdym stanie i pokazuje, ile czeka na montaż
- mapa sama przybliża się tak, żeby były widoczne wszystkie pinezki. Bez czujników pokazuje całą Polskę
- **☰** w górnym pasku otwiera menu: zmiana hasła, wylogowanie, motyw, język, instalacja aplikacji

## Dane

`GET /sensors` ([api.md, sekcja 2](../backend/api.md#2-czujniki-mapa), gdzie jest jeszcze pod polską nazwą `/czujniki`). Leśniczy dostaje czujniki swojego leśnictwa, nadleśniczy wszystkie. Ten sam endpoint pobiera tabela w panelu admina.

- lista odświeża się **co 60 s**, bez przeładowania mapy. Nowe alarmy mają też przychodzić pushem
- gdy odświeżenie się nie uda, pinezki zostają, a nad mapą pojawia się komunikat
- endpointu nie ma jeszcze na backendzie, więc mapa działa tylko na mocku (`VITE_USE_MOCK=true`)

## Technicznie

- **Leaflet** (`react-leaflet`) i kafelki **OpenStreetMap**: darmowe, bez klucza API. 
- pinezki to `divIcon` (zwykły element HTML z klasami Tailwind), a nie domyślne ikony Leafleta, które mają problem ze ścieżkami do obrazków po zbudowaniu. Pinezka ma tytuł „Nazwa: Stan”, więc działa też z klawiatury i czytnikiem ekranu
- stany i kolory są w `src/lib/sensor-status.ts`, wspólne dla mapy i tabeli admina
- mapa ładuje się osobno (`React.lazy` w `App.tsx`), bo Leaflet ma ok. 150 kB. Logowanie i panel admina go nie pobierają

## Ograniczenia
- bez internetu mapa nie pokaże podkładu. Kafelki nie są zapisywane w pamięci aplikacji
