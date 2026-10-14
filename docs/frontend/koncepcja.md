# Koncepcja aplikacji

## Co robi aplikacja

Leśniczy oznacza w aplikacji, które mygły mają zostać w lesie, a które wydane do wywozu. Gdy czujnik wykryje kradzież, leśniczy dostaje powiadomienie na telefon i widzi na mapie, gdzie to jest. Nadleśniczy w biurze przegląda zestawienia alarmów, a administrator zakłada konta.

## Ustalenia

- **Platformy:** Android (leśniczy w terenie) + przeglądarka na komputerze (nadleśniczy, administrator).


## Pomysły
- Numeracja czujników – leśniczy sam nadaje numery swoim detektorom (sposób do ustalenia)
- Lokalizacja mygły z GPS telefonu leśniczego: aplikacja pobiera pozycję i przypisuje czujnik do mygły.

## Widoki

| Widok | Dla kogo | Zawartość |
|---|---|---|
| Alarmy | leśniczy | lista alarmów „ruszono mygłę X”, powiadomienia, odpowiedź „fałszywy alarm” / „złapany” |
| Mapa mygieł | leśniczy, nadleśniczy | mygły ze statusem: niewydana / wydana do wywozu / alarm / czujnik milczy |
| Raporty | nadleśniczy | zestawienie alarmów i zdarzeń, wykresy |
| Panel administracyjny | administrator | użytkownicy i role |

## Stack (propozycja)

| Warstwa | Wybór |
|---|---|
| Framework | React + TypeScript |
| Budowanie | Vite |
| Komponenty UI | do wyboru (porównanie poniżej) |
| Mapa | Leaflet (`react-leaflet`) + OpenStreetMap |

### Komponenty UI

| Biblioteka | Stylowanie | Gotowe komponenty |
|---|---|---|
| Tailwind | klasy CSS | brak |
| shadcn/ui | Tailwind | tak (kod kopiowany do projektu) |
| Mantine | CSS Modules | tak (npm) |
| MUI | CSS-in-JS (Emotion) | tak (npm) |


Potrzebne endpointy:
- logowania
- pobrania listy mygieł i zmiany ich statusu
- przypisania czujnika do miejsca zbierania drewna
- pobrania listy alarmów i zapisania odpowiedzi leśniczego
- pobrania zestawień do raportów
- zapisu subskrypcji powiadomień push
- pobrania listy użytkowników i zakładania kont

----
FCM - Firebase Cloud Messaging 
Za pomocą subskrypcji ("adres skrzynki" na którą przychodzą powiadomienia) telefon może odbierać powiadomienia od serwera

Powiadomienia push na telefonie potrzebują https -> testowanie razem za pomocą [LocalTunnel](https://theboroer.github.io/localtunnel-www/) (bądź inne podobne narzędzia)

