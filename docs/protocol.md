# Protokół – ramki urządzenie ↔ serwer

> Szkic od backendu (Kacper). Dopisujcie uwagi w PR, zwłaszcza Damian, Kiryl i Martyna. Nic tu nie jest ostateczne. 
## Co ustaliliśmy (i co to zmienia)
 
- **Łączność: LoRaWAN** (na testy publiczna sieć TTN lub drugim microkontrolerze, LoPy). 
- **Komunikacja jednostronna**: tylko urządzenie → serwer. Nie ma żadnych komend w dół.
- **Czujnik obszarowy (obok stosu drewna)**. Główny czujniki to **mikrofon**, czujnik wibracji.
- **Detekcja działa na urządzeniu**. Wysyłamy tylko wynik i parę liczb, żadnego surowego dźwięku.
- **GPS jest w terminalu/telefonie leśniczego**, nie w urządzeniu. Lokalizację mygły zapisujemy raz przy montażu.



## Ogólnie

- Wysyłamy **bajty, nie JSON**. Łącze to kilkadziesiąt bajtów na wiadomość (chyba)
- Celujemy w max ~20 B na ramkę.
-  **Limit czasu nadawania:** TTN daje ~30 s nadawania na dobę na urządzenie (fair use), a do tego jest 1% duty cycle. Przy SF12 jedna nasza ramka to ok. 1 s w eterze, czyli **max ok. 25 wiadomości na dobę** w najgorszym przypadku. Heartbeat co 6 h (4/dobę) i alarmy mieszczą się spokojnie.\
- **Co daje sieć (nie wysyłamy tego w ramce):**
  - ID urządzenia (DevEUI w LoRaWAN)
  -  Lokalizacja
  - czas odbioru,

-  **szyfrowanie i podpis**: LoRaWAN szyfruje (AES-128) i podpisuje każdą ramkę sam, a TTN wysyła nam ją po HTTPS. Nie musimy robić własnego szyfrowania chyba.
- ID urządzenia i czas odbioru powinna nam dać sieć, więc nie wysyłamy ich w ramce.
-  Lokalizacja też nie, bo czujnik się nie rusza i wpisujemy ją raz w bazie z poziomu terminala leśniczego ją pobieramy.
- Kolejność bajtów: big-endian(kto był na programowaniu sieciowym pamięta).

**Filtrowanie jest w dwóch miejscach:** - w przypadku braku możliwości wysłania drgań
1. **Na urządzeniu** – algorytm Kiryla decyduje, czy to piła. Wysyłamy tylko wynik i parę liczb, żadnych surowych drgań.
2. **Na serwerze** – sprawdzamy rzeczy, których jedno urządzenie nie wie, i dopiero wtedy decydujemy, czy wysłać push do leśniczego.(jeszcze nie wiem co)

## Nagłówek (każda ramka z urządzenia) 

| bajt | co | uwagi |
|---|---|---|
| 0 (górne 4 bity) | wersja | wersja **formatu ramki**, nie urządzenia. Jak zmienimy układ pól, to podbijamy, żeby serwer wiedział, jak czytać stare i nowe. Startujemy od 1. W prototypie może przesada, ale kosztuje pół  bajtu  |
| 0 (dolne 4 bity) | typ | jaka to wiadomość (lista niżej) |
| 1–2 | licznik | +1 przy każdej ramce. Po to, żeby wyłapać duplikaty lub jakieś zbierzności jeszcze nie wiem czy to potrzebne, zgubione ramki. Musi przetrwać restart nie wiem czy to potrzebne w LoraWan |

Np. `0x11` = wersja 1, typ 1 (alarm).

> Opcja: W lorze wydaje się możliwe oszczędzenie w kilku miejscach do doczytania

## Typy

| typ | nazwa | kiedy |
|---|---|---|
| 1 | ALARM | wykryto "kradzież", po tym urządzenie się blokuje |
| 2 | HEARTBEAT | co ~6 h, „żyję” + bateria czas do określenia |
| 3 | BOOT | po włączeniu/restarcie | 
 
- jak coś wymyślicie, to dopiszcie


### ALARM – 10 B
 
| bajt | pole | uwagi |
|---|---|---|
| 0–2 | nagłówek | |
| 3 | rodzaj zdarzenia |  **Listę ustala Kiryl**, na razie przykładowa |
| 4 | źródło (bity) | bit0 = mikrofon, bit1 = akcelerometr. Jak oba, to alarm pewniejszy |
| 5 | pewność 0–100 | jak bardzo algorytm jest pewny. Skalę ustala Kiryl, na razie ją daję |
| 6–7 | czas trwania [s] | czy to było stuknięcie, czy 10 minut ładowania |
| 8 | głośność / energia 0–255 | jak głośno/mocno. Nie wiem czy potrzebne |
| 9 | bateria % | |
 
> Zmiany: zamiast „częstotliwości z FFT” są rodzaj zdarzenia i źródło, bo pod mikrofon to bardziej przydatne. Częstotliwość wróci, jeśli Kiryl powie, że ma sens.


### HEARTBEAT – 6 B

| bajt | pole | uwagi |
|---|---|---|
| 0–2 | nagłówek | |
| 3 | bateria % | |
| 4 | odrzucone zdarzenia | ile razy się obudził i stwierdził, że to nie kradzież. Dane dla Kiryla, plus jak jest dużo przy ciszy, to pewnie czujnik padł, nie wiem czy to bedzie tak działać, do tego nie wiem jak to by miało dizałąć z czujnikiem wibracji i alramem mysle że musmy to omówić |
| 5 | flagi | bit0 zablokowany, bit1 niska bateria, bit2 błąd czujnika |

Jak heartbeat nie przyjdzie przez ~12 h, serwer daje alarm „czujnik milczy” (zerwany, rozładowany, zagłuszony…).


### BOOT – 6 B

nagłówek + wersja firmware + przyczyna restartu (1 normalne włączenie, 2 watchdog, 3 za niskie napięcie) + bateria.
Jak urządzenie restartuje się co chwilę przez watchdog, to mamy buga.

## Blokada po alarmie
 
Urządzenie ma się budzić jak najrzadziej. Po wysłaniu alarmu **blokuje się** i nie wysyła kolejnych **do upływu timeoutu** (np. 1 h).
 
```
SEN --dźwięk/drgania--> ANALIZA --kradzież--> wyślij ALARM --> ZABLOKOWANY
 ^                         |                                       |
 |-------nie kradzież------|                                       |
 |------------------------- timeout (np. 1 h) ---------------------|
```
 
Komunikacja jest jednostronna, więc **odpowiedź leśniczego („fałszywy alarm” / „złapany”) nie idzie do urządzenia**, tylko zostaje na serwerze. Zamyka alarm w apce i jest etykietą dla Kiryla.
 


## Co robi serwer
 
1. Przychodzi webhook z TTN → wyciągamy DevEUI, ramkę (base64), czas odbioru i RSSI/SNR. 
2. DevEUI → szukamy urządzenia w bazie (nieznane = olewamy i logujemy) → z niego mygła i leśnictwo
3. sprawdzamy wersję
4. licznik: mniejszy lub równy ostatniemu = duplikat, wywalamy; przeskok = logujemy, że coś zginęło; po BOOT akceptujemy nowy licznik
5. dekodujemy do JSON-a i zapisujemy w bazie
6. dla alarmu filtrowanie (niżej) i ewentualnie push


Przykład: `11 00 2A 01 01 57 00 28 B4 40` →
 
```json
{
  "device_id": "sensor-007",
  "mygla": "M-12",
  "type": "ALARM",
  "counter": 42,
  "event": "podbieranie",
  "source": ["mikrofon"],
  "confidence": 87,
  "duration_s": 40,
  "energy": 180,
  "battery_pct": 64,
  "rssi": -112,
  "received_at": "2026-10-09T11:52:10Z"
}
```


Dekoder w Pythonie:

- TODO (będzie w `backend/app/protocol/decoder.py` z testami)

# Filtrowanie na serwerze – pomysły
 
- **Mygła wydana do wywozu** (leśniczy potwierdził w apce) → alarmy z niej wyciszamy w czasie wywozu. Najważniejsza reguła, bez niej każdy legalny wywóz to alarm - nie wiem może da się inaczej to rozwiązać

- pół lasu naraz - raczej wichura albo burza
- silny wiatr z API pogodowego - obniżamy ocenę ??? nie wiem, czy to ma sens przy mikrofonie, może przy wietrze jest głośno
- czujnik, który często daje fałszywe alarmy (wg odpowiedzi leśniczych) - obniżamy

 
Fajny bonus: odpowiedzi leśniczych (fałszywy/prawdziwy) zapisujemy razem z alarmem, więc Kiryl dostaje oznaczone dane z terenu.


## Do ustalenia
 

- [ ] **Kiryl:** jakie rodzaje zdarzeń algorytm umie rozróżnić i jaka skala pewności? Czy częstotliwość ma sens?
- [ ] **Damian:** licznik zostaje (2 B) czy na LoRa polegamy na FCnt? Gdzie go trzymać, żeby przetrwał restart?
- [ ] **Wojtek / Damian:** zostaje akcelerometr czy to drugie, czyli da się TAMPER?
- [ ] **wszyscy:** timeout blokady i co ile heartbeat, jak zmierzymy zużycie baterii

