# Firmware

**Odpowiedzialny:** Damian

## Przykłady

- [przyklady/wyslij_wifi.py](przyklady/wyslij_wifi.py) – LoPy przez Wi-Fi wysyła ramki wg protokołu prosto na backend (bez TTN), w tej samej sieci (`http://IP:8000`) albo przez tunel HTTPS (`https://…trycloudflare.com`), z kluczem `X-Ingest-Key`. Konfiguracja i sprawdzenie wyniku: [docs/testowanie.md](../docs/testowanie.md#6-płytka-lopy-przez-wi-fi)
