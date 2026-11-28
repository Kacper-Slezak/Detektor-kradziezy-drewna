from network import LoRa
import socket
import time
import ubinascii
import struct
import pycom


# ============================================================
# DANE URZADZENIA Z THE THINGS NETWORK
# ============================================================
# DEV_EUI  - 16 znakow
# JOIN_EUI - 16 znakow, dawniej AppEUI
# APP_KEY  - 32 znaki
# ============================================================

DEV_EUI = ""
JOIN_EUI = ""
APP_KEY = ""


# Co ile sekund wysylac licznik
CZAS_MIEDZY_WIADOMOSCIAMI = 30


def sprawdz_dane():
    if len(DEV_EUI) != 16:
        print("BLAD: DEV_EUI musi miec 16 znakow.")
        return False

    if len(JOIN_EUI) != 16:
        print("BLAD: JOIN_EUI musi miec 16 znakow.")
        return False

    if len(APP_KEY) != 32:
        print("BLAD: APP_KEY musi miec 32 znaki.")
        return False

    return True


def na_hex(dane):
    return ubinascii.hexlify(dane).decode("utf-8").upper()


def odczytaj_downlink(dane):
    try:
        return dane.decode("utf-8")
    except:
        return "Nie jest to tekst. HEX: " + na_hex(dane)


# ============================================================
# START PROGRAMU
# ============================================================

pycom.heartbeat(False)

# Niebieska dioda - uruchamianie
pycom.rgbled(0x000020)

print("")
print("==========================================")
print(" LoPy - polaczenie z The Things Network")
print("==========================================")

if not sprawdz_dane():
    pycom.rgbled(0x200000)
    raise ValueError("Popraw DEV_EUI, JOIN_EUI oraz APP_KEY")


# Zamiana tekstu HEX na bajty
dev_eui = ubinascii.unhexlify(DEV_EUI)
join_eui = ubinascii.unhexlify(JOIN_EUI)
app_key = ubinascii.unhexlify(APP_KEY)


print("DevEUI: ", DEV_EUI)
print("JoinEUI:", JOIN_EUI)
print("Region: EU868")
print("")


# ============================================================
# INICJALIZACJA LORAWAN
# ============================================================

lora = LoRa(
    mode=LoRa.LORAWAN,
    region=LoRa.EU868
)


# ============================================================
# DOLACZANIE DO TTN PRZEZ OTAA
# ============================================================

print("Rozpoczynam OTAA Join...")

lora.join(
    activation=LoRa.OTAA,
    auth=(dev_eui, join_eui, app_key),
    timeout=0
)


numer_proby = 0

while not lora.has_joined():
    numer_proby += 1
    print("Jeszcze nie polaczono. Oczekiwanie... Proba:", numer_proby)

    # Niebieska dioda podczas oczekiwania
    pycom.rgbled(0x000020)

    time.sleep(2.5)


print("")
print("==========================================")
print(" SUKCES - LoPy dolaczylo do TTN")
print("==========================================")

# Zielona dioda - polaczono
pycom.rgbled(0x002000)


# ============================================================
# UTWORZENIE SOCKETU LORAWAN
# ============================================================

s = socket.socket(socket.AF_LORA, socket.SOCK_RAW)

# Data Rate 5 dla EU868
s.setsockopt(socket.SOL_LORA, socket.SO_DR, 5)

# Wylaczenie potwierdzonych uplinkow
try:
    s.setsockopt(socket.SOL_LORA, socket.SO_CONFIRMED, False)
except:
    print("Firmware nie obsluguje SO_CONFIRMED - pomijam.")


# ============================================================
# PETLA WYSYLANIA I ODBIERANIA
# ============================================================

licznik = 0

while True:
    licznik += 1

    # Licznik zapisany jako 4 bajty:
    # 1 = 00000001
    # 2 = 00000002
    # 3 = 00000003
    payload = struct.pack(">I", licznik)

    print("")
    print("------------------------------------------")
    print("Wysylam uplink do TTN")
    print("Licznik:", licznik)
    print("Payload HEX:", na_hex(payload))

    try:
        # Tryb blokujacy:
        # LoPy wysyla dane i czeka na okna odbiorcze RX1/RX2
        s.setblocking(True)

        # W LoPy uzywamy send(), a nie sendto()
        liczba_bajtow = s.send(payload)

        print("Uplink wyslany prawidlowo.")
        print("Wyslano bajtow:", liczba_bajtow)

        # Fioletowa dioda - wyslano uplink
        pycom.rgbled(0x200020)

    except Exception as blad:
        print("BLAD WYSYLANIA:", blad)

        # Czerwona dioda - blad
        pycom.rgbled(0x200000)

    # Po wyslaniu przechodzimy do odbioru nieblokujacego
    s.setblocking(False)

    print("Sprawdzam, czy odebrano downlink...")

    try:
        dane = s.recv(256)

        if dane:
            print("")
            print("****************************************")
            print(" ODEBRANO DOWNLINK Z TTN")
            print("****************************************")
            print("Liczba bajtow:", len(dane))
            print("Payload HEX:", na_hex(dane))
            print("Wiadomosc:", odczytaj_downlink(dane))
            print("****************************************")

            # Turkusowa dioda - odebrano downlink
            pycom.rgbled(0x002020)

        else:
            print("Brak downlinku po tym uplinku.")
            pycom.rgbled(0x002000)

    except Exception as blad:
        # Brak danych w nieblokujacym recv jest normalny
        print("Brak downlinku po tym uplinku.")
        pycom.rgbled(0x002000)

    print("Nastepny uplink za", CZAS_MIEDZY_WIADOMOSCIAMI, "sekund.")

    time.sleep(CZAS_MIEDZY_WIADOMOSCIAMI)
