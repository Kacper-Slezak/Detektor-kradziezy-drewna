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

