"""Test bez TTN: LoPy łączy się z Wi-Fi i wysyła ramki prosto na backend (POST /api/v1/ingest).

To samo co `curl`, tylko z płytki. Ramki są pakowane wg protokołu
(ten sam układ co backend/app/protocol/encoder.py), więc backend zapisze je jak prawdziwe.

Backend jest osiągalny na trzy sposoby (API_URL):
- ta sama sieć:  http://192.168.1.20:8000  (IP laptopa),
- tunel HTTPS:   https://xyz.trycloudflare.com  (cloudflared tunnel --url http://localhost:8000),
  wtedy płytka może być w dowolnej sieci z internetem (np. hotspot z telefonu),
- tunel TCP bez TLS: http://bore.pub:41235  (gdy TLS na płytce nie działa, np. MBEDTLS_ERR_SSL_ALLOC_FAILED).

Jak użyć:
1. Uzupełnij WIFI_SSID, WIFI_HASLO, API_URL, DEVICE_ID i INGEST_KEY
   (czujnik musi istnieć w bazie: czujnik demo albo dodany w panelu admina;
   INGEST_KEY = INGEST_API_KEY z backend/.env, pusty, gdy backend działa bez klucza).
2. Wgraj na płytkę i uruchom (Pymakr: Upload, albo w REPL: exec(open('wyslij_wifi.py').read())).
3. Sprawdź wynik wg docs/testowanie.md, sekcja „Test z płytki przez Wi-Fi”.

Plik działa też na zwykłym Pythonie na laptopie (bez Wi-Fi), żeby sprawdzić backend albo tunel:
    python firmware/przyklady/wyslij_wifi.py                                   # http://127.0.0.1:8000
    python firmware/przyklady/wyslij_wifi.py https://xyz.trycloudflare.com KLUCZ
"""

import struct
import time

try:  # MicroPython na LoPy
    import ubinascii as binascii
    import usocket as socket
    import ussl as ssl
    from network import WLAN

    NA_PLYTCE = True
except ImportError:  # zwykły Python na laptopie
    import binascii
    import socket
    import ssl
    import sys

    NA_PLYTCE = False

# ---------- do uzupełnienia ----------
WIFI_SSID = "nazwa-sieci"
WIFI_HASLO = "haslo-sieci"
API_URL = "http://192.168.1.20:8000"  # IP laptopa w tej samej sieci albo adres tunelu https://…
DEVICE_ID = "70B3D57ED00D0009"  # czujnik demo "Skład na Kopcu" (seed --demo)
INGEST_KEY = ""  # INGEST_API_KEY z backend/.env (pusty, gdy backend działa bez klucza)
# --------------------------------------

if not NA_PLYTCE:
    API_URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
    INGEST_KEY = sys.argv[2] if len(sys.argv) > 2 else INGEST_KEY

WERSJA = 1
ALARM, HEARTBEAT, BOOT = 1, 2, 3


def ramka_boot(licznik, bateria, firmware=1, przyczyna=1):
    return struct.pack(">BHBBB", (WERSJA << 4) | BOOT, licznik, firmware, przyczyna, bateria)


def ramka_heartbeat(licznik, bateria, odrzucone=0, flagi=0):
    return struct.pack(">BHBBB", (WERSJA << 4) | HEARTBEAT, licznik, bateria, odrzucone, flagi)


def ramka_alarm(licznik, bateria, pewnosc=90, czas_s=60, energia=200, zrodla=0b11, rodzaj=1):
    # zrodla: bit0 = mikrofon, bit1 = wibracje
    return struct.pack(
        ">BHBBBHBB", (WERSJA << 4) | ALARM, licznik, rodzaj, zrodla, pewnosc, czas_s, energia, bateria
    )


def rozbierz_url(url):
    """'https://host[:port][/prefiks]' -> (https?, host, port, prefiks). Bez urllib (brak na LoPy)."""
    schemat, _, reszta = url.partition("://")
    if schemat not in ("http", "https"):
        raise ValueError("API_URL musi zaczynać się od http:// albo https://")
    https = schemat == "https"
    adres, _, sciezka = reszta.partition("/")
    host, _, port = adres.partition(":")
    port = int(port) if port else (443 if https else 80)
    prefiks = ("/" + sciezka).rstrip("/")
    return https, host, port, prefiks


HTTPS, HOST, PORT, PREFIKS = rozbierz_url(API_URL)


def polacz_wifi():
    if not NA_PLYTCE:
        return
    wlan = WLAN(mode=WLAN.STA)
    wlan.connect(WIFI_SSID, auth=(WLAN.WPA2, WIFI_HASLO), timeout=10000)
    for _ in range(40):
        if wlan.isconnected():
            print("Wi-Fi OK, IP płytki:", wlan.ifconfig()[0])
            return
        time.sleep(0.5)
    raise OSError("Brak połączenia z Wi-Fi " + WIFI_SSID)


def otworz_socket():
    """TCP, a dla https dodatkowo TLS z SNI (tunel rozpoznaje subdomenę po server_hostname).

    Certyfikat nie jest sprawdzany na płytce (brak pliku CA): to skrypt testowy,
    klucz X-Ingest-Key i tak idzie zaszyfrowany.
    """
    rodzina, _, _, _, adres = socket.getaddrinfo(HOST, PORT)[0]  # localhost bywa IPv6
    s = socket.socket(rodzina, socket.SOCK_STREAM)
    s.settimeout(15)
    if HTTPS:
        if NA_PLYTCE:
            # Pycom: wrap przed connect, handshake przy connect
            s = ssl.wrap_socket(s, server_hostname=HOST)
        else:
            s = ssl.create_default_context().wrap_socket(s, server_hostname=HOST)
    s.connect(adres)
    return s


def odchunkuj(tresc):
    """Transfer-Encoding: chunked (proxy tunelu potrafi tak odesłać): '<hex>\\r\\n<dane>\\r\\n'… '0\\r\\n'."""
    wynik = b""
    while True:
        rozmiar, _, tresc = tresc.partition(b"\r\n")
        n = int(rozmiar.split(b";")[0], 16)
        if n == 0:
            return wynik
        wynik += tresc[:n]
        tresc = tresc[n + 2 :]


def wyslij(ramka):
    """POST /api/v1/ingest na gołym sockecie (LoPy nie ma wbudowanego urequests)."""
    payload_hex = binascii.hexlify(ramka).decode()
    body = '{"device": "%s", "payload_hex": "%s"}' % (DEVICE_ID, payload_hex)
    host_naglowek = HOST if PORT in (80, 443) else "%s:%d" % (HOST, PORT)
    zapytanie = (
        "POST %s/api/v1/ingest HTTP/1.1\r\n"
        "Host: %s\r\n"
        "User-Agent: detektor-lopy\r\n"
        "Connection: close\r\n"
        "Content-Type: application/json\r\n"
        "X-Ingest-Key: %s\r\n"
        "Content-Length: %d\r\n"
        "\r\n%s"
    ) % (PREFIKS, host_naglowek, INGEST_KEY, len(body), body)

    s = otworz_socket()
    try:
        dane = zapytanie.encode()
        while dane:  # send może wysłać tylko część
            dane = dane[s.send(dane) :]
        odpowiedz = b""
        while True:
            kawalek = s.recv(512)
            if not kawalek:
                break
            odpowiedz += kawalek
    finally:
        s.close()

    naglowki, _, tresc = odpowiedz.partition(b"\r\n\r\n")
    kod = int(naglowki.split(b" ")[1])
    if b"transfer-encoding: chunked" in naglowki.lower():
        tresc = odchunkuj(tresc)
    print(payload_hex.upper(), "->", kod, tresc.decode())
    return kod, tresc


def main():
    polacz_wifi()
    print("Backend:", API_URL)
    # BOOT na start: po restarcie licznik zaczyna od nowa, a backend po BOOT go akceptuje.
    # Bez tego ramki z licznikiem nie większym niż ostatnio zapisany wracają jako "duplicate".
    wyslij(ramka_boot(1, bateria=88))
    wyslij(ramka_heartbeat(2, bateria=88))
    # alarm jak w firmware: 3 razy, backend scali je w jeden
    for i in range(3):
        wyslij(ramka_alarm(3 + i, bateria=88))
        time.sleep(2)


main()
