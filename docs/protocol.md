# Protokół – ramki urządzenie ↔ serwer

> Szkic od backendu (Kacper). Dopisujcie uwagi w PR, zwłaszcza Damian, Kiryl i Martyna. Nic tu nie jest ostateczne.

## Ogólnie

- Wysyłamy **bajty, nie JSON**. Łącze to kilkadziesiąt bajtów na wiadomość (chyba)
- Celujemy w max ~20 B na ramkę.
- ID urządzenia i czas odbioru powinna nam dać sieć, więc nie wysyłamy ich w ramce. Lokalizacja też nie, bo drzewo się nie rusza i wpisujemy ją raz w bazie z poziomu terminala leśniczego ją pobieramy .
- Kolejność bajtów: big-endian(kto był na programowaniu sieciowym pamięta).

**Filtrowanie jest w dwóch miejscach:** - w przypadku braku możliwości wysłania drgań
1. **Na urządzeniu** – algorytm Kiryla decyduje, czy to piła. Wysyłamy tylko wynik i parę liczb, żadnych surowych drgań.
2. **Na serwerze** – sprawdzamy rzeczy, których jedno urządzenie nie wie, i dopiero wtedy decydujemy, czy wysłać push do leśniczego.(jeszcze nie wiem co)

## Nagłówek (każda ramka z urządzenia) 

| bajt | co | uwagi |
|---|---|---|
| 0 (górne 4 bity) | wersja | wersja **formatu ramki**, nie urządzenia. Jak zmienimy układ pól, to podbijamy, żeby serwer wiedział, jak czytać stare i nowe. Startujemy od 1, to mi internet podpowiedział nie wiem czy ma sens w prototypie ale w produkcie ma dlamnie |
| 0 (dolne 4 bity) | typ | jaka to wiadomość (lista niżej) |
| 1–2 | licznik | +1 przy każdej ramce. Po to, żeby wyłapać duplikaty lub jakieś zbierzności jeszcze nie wiem czy to potrzebne, zgubione ramki. Musi przetrwać restart |

Np. `0x11` = wersja 1, typ 1 (alarm).

## Typy

| typ | nazwa | kiedy |
|---|---|---|
| 1 | ALARM | wykryto "kradzież", po tym urządzenie się blokuje |
| 2 | HEARTBEAT | co ~6 h, „żyję” + bateria czas do określenia |
| 3 | BOOT | po włączeniu/restarcie | 

- jak coś wymyślicie to dopiszcie
- Moim pomysłem był by też jakiś Alarm osobno dla ruchu osobno dla dźwięku powiedzmy że któś się za bardzo zainteresował naszym czujnikiem i go wziął albo coś ?? też może jakiś sposób znajdowania go ?? jak już rozkrandą drewno no to on gdzieśspadnie poleci itp., chyab że to co mówiłem tymonowi jest on jakoś z boku nie w stosie na stosie tlylko jako galąź obok 

### ALARM – 9 B

| bajt | pole | uwagi |
|---|---|---|
| 0–2 | nagłówek | |
| 3 | pewność 0–100 | jak bardzo algorytm jest pewny, że to piła. Skalę ustala Kiryl, nie wiem czy będzie skala narazie ją daje |
| 4–5 | czas trwania [s] | czy to było stuknięcie, czy 40 s piłowania, nie mam pojęcia czy to będzie ale brzmi spoko |
| 6 | częstotliwość ×10 Hz | główna częstotliwość z FFT; **do pogadania z Kirylem**, czy to w ogóle ma sens |
| 7 | energia 0–255 | jak mocno trzęsie, rozumiem to jako czujnik nie dźwięku ale drgań/ruchu  |
| 8 | bateria % | |


### HEARTBEAT – 6 B

| bajt | pole | uwagi |
|---|---|---|
| 0–2 | nagłówek | |
| 3 | bateria % | |
| 4 | odrzucone zdarzenia | ile razy się obudził i stwierdził, że to nie piła. Dane dla Kiryla, plus jak jest dużo przy ciszy, to pewnie czujnik padł, nie wiem czy to bedzie tak działać |
| 5 | flagi | bit0 zablokowany, bit1 niska bateria, bit2 błąd czujnika |

Jak heartbeat nie przyjdzie przez ~12 h, serwer daje alarm „czujnik milczy” (zerwany, rozładowany, zagłuszony…).


### BOOT – 6 B

nagłówek + wersja firmware + przyczyna restartu (1 normalne włączenie, 2 watchdog, 3 za niskie napięcie) + bateria.
Jak urządzenie restartuje się co chwilę przez watchdog, to mamy buga.

