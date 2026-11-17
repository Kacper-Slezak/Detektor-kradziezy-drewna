# Montaż czujnika

Admin dodaje czujnik w panelu (bez lokalizacji), a leśniczy montuje go na miejscu: staje przy składzie, nadaje nazwę i zapisuje pozycję z GPS telefonu. Od tej chwili czujnik ma pinezkę na mapie.

## Jak to wygląda

1. w legendzie mapy jest napis „1 czujnik czeka na montaż”, a pod nim przycisk **Zamontuj** (tylko leśniczy, nadleśniczy widzi sam napis)
2. z boku wysuwa się panel **Montaż czujnika**:
   - **Czujnik**: czujniki swojego leśnictwa bez lokalizacji. Gdy jest jeden, jest od razu wybrany. Gdy admin nadał już nazwę, wpisuje się w pole **Nazwa**
   - **Nazwa**: wymagana, do 100 znaków, np. „Skład przy drodze 5”
   - **Pobierz pozycję**: telefon pyta o zgodę na lokalizację, potem widać współrzędne i dokładność, np. `50.06123, 19.95123 · ±8 m`. Przycisk zmienia się na **Pobierz ponownie**
   - przy dokładności gorszej niż **50 m** pojawia się ostrzeżenie „Słaba dokładność, spróbuj ponownie na otwartym terenie”. Zapisać i tak można
   - **Zapisz** jest aktywny, gdy jest wybrany czujnik, nazwa i pozycja
3. po zapisaniu panel się zamyka, nad mapą pojawia się „Zamontowano: Skład przy drodze 5”, a mapa od razu pobiera czujniki na nowo
4. nowa pinezka jest pomarańczowa („Bez kontaktu”), dopóki czujnik nic nie wyśle. Po pierwszej ramce robi się zielona

Przyciski i pola mają ok. 48 px wysokości, żeby dało się trafić kciukiem w terenie.

## Gdy nie ma pozycji

| Komunikat | Przyczyna |
|---|---|
| Brak zgody na lokalizację… | użytkownik odmówił. Zgodę przywraca się w przeglądarce: kłódka przy adresie → Uprawnienia → Lokalizacja |
| Nie udało się ustalić pozycji… | brak sygnału GPS albo wyłączona lokalizacja w telefonie |
| Szukanie pozycji trwało za długo… | nie ma pozycji po 20 s (np. gęsty las); można spróbować ponownie |
| Lokalizacja działa tylko na stronie https | strona otwarta przez `http://` z adresem IP |
| Ta przeglądarka nie podaje lokalizacji | bardzo stara przeglądarka |

## Dane

`PUT /sensors/{id}/mount` z `{ "name", "lat", "lon" }` ([api.md, sekcja 2](../backend/api.md#put-apiv1sensorsidmount)). Lista czujników do montażu to czujniki z mapy bez lokalizacji, więc nie ma osobnego zapytania.

- montuje tylko **leśniczy** i tylko czujnik swojego leśnictwa. Nadleśniczy i cudzy czujnik dostają `403`
- po montażu czujnik jest włączony (`active: true`), ma stan `silent`, dopóki nie wyśle pierwszej ramki
- na mocku (`VITE_USE_MOCK=true`) czeka na montaż po jednym czujniku w Dąbrowie (`blazej`) i w Olszynach (`nowy.lesniczy`)

## Technicznie

- `src/lib/geolocation.ts`: `getPosition()` opakowuje `navigator.geolocation`. Prosi o prawdziwy GPS (`enableHighAccuracy`), zawsze o świeżą pozycję, czeka do 20 s. Błędy zwraca jako kody, a teksty są w `mount.errors.*` (pl/en)
- `src/components/MountSensorForm.tsx`: formularz, `MapPage` otwiera go w panelu bocznym


## Dalej
- przeniesienie zamontowanego czujnika (backend to umożliwia: ponowny montaż nadpisuje nazwę i pozycję)
- wybór miejsca palcem na mapie, gdy GPS jest słaby
- wydania drewna (wyciszanie czujnika na czas wywozu)
