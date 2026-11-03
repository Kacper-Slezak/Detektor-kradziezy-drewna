"""Test bez TTN: LoPy łączy się z Wi-Fi i wysyła ramki prosto na backend (POST /api/v1/ingest).

To samo co `curl`, tylko z płytki. Ramki są pakowane wg protokołu
(ten sam układ co backend/app/protocol/encoder.py), więc backend zapisze je jak prawdziwe.

Jak użyć:
1. Uzupełnij WIFI_SSID, WIFI_HASLO, API_HOST (IP laptopa z backendem) i DEVICE_ID
   (czujnik musi istnieć w bazie: czujnik demo albo dodany w panelu admina).
2. Wgraj na płytkę i uruchom (Pymakr: Upload, albo w REPL: exec(open('wyslij_wifi.py').read())).
3. Sprawdź wynik wg docs/testowanie.md, sekcja „Test z płytki przez Wi-Fi”.

Plik działa też na zwykłym Pythonie na laptopie (bez Wi-Fi), żeby sprawdzić, czy backend odpowiada:
    python firmware/przyklady/wyslij_wifi.py
"""

import struct
import time

try:  # MicroPython na LoPy
    import ubinascii as binascii
    import usocket as socket
    from network import WLAN

    NA_PLYTCE = True
except ImportError:  # zwykły Python na laptopie
    import binascii
    import socket

    NA_PLYTCE = False

# ---------- do uzupełnienia ----------
WIFI_SSID = "nazwa-sieci"
WIFI_HASLO = "haslo-sieci"
API_HOST = "192.168.1.20"  # IP laptopa w tej samej sieci
API_PORT = 8000
DEVICE_ID = "70B3D57ED00D0009"  # czujnik demo "Skład na Kopcu" (seed --demo)
# --------------------------------------

if not NA_PLYTCE:
    API_HOST = "localhost"

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


def wyslij(ramka):
    """POST /api/v1/ingest na gołym sockecie (LoPy nie ma wbudowanego urequests)."""
    payload_hex = binascii.hexlify(ramka).decode()
    body = '{"device": "%s", "payload_hex": "%s"}' % (DEVICE_ID, payload_hex)
    zapytanie = (
        "POST /api/v1/ingest HTTP/1.0\r\n"
        "Host: %s:%d\r\n"
        "Content-Type: application/json\r\n"
        "Content-Length: %d\r\n"
        "\r\n%s"
    ) % (API_HOST, API_PORT, len(body), body)

    adres = socket.getaddrinfo(API_HOST, API_PORT)[0][-1]
    s = socket.socket()
    s.settimeout(10)
    try:
        s.connect(adres)
        s.send(zapytanie.encode())
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
    print(payload_hex.upper(), "->", kod, tresc.decode())
    return kod, tresc


def main():
    polacz_wifi()
    # BOOT na start: po restarcie licznik zaczyna od nowa, a backend po BOOT go akceptuje.
    # Bez tego ramki z licznikiem nie większym niż ostatnio zapisany wracają jako "duplicate".
    wyslij(ramka_boot(1, bateria=88))
    wyslij(ramka_heartbeat(2, bateria=88))
    # alarm jak w firmware: 3 razy, backend scali je w jeden
    for i in range(3):
        wyslij(ramka_alarm(3 + i, bateria=88))
        time.sleep(2)


main()
