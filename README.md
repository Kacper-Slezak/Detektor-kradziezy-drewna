# Detektor kradzieży drewna

Projekt z przedmiotu IoT (AGH). Urządzenie ukryte w okolicy mygły (stosie drewna przy drodze leśnej) wykrywa podbieranie drewna i wysyła alarm do leśniczego.

## Problem

Przewoźnik jest w lesie legalnie, z dokumentami na wywóz jednej mygły, i przy okazji ładuje drewno z sąsiedniej. Braki wychodzą dopiero przy inwentaryzacji, a wtedy nie da się ich przypisać konkretnemu wywozowi.

### Decyzje
- Wykrywamy podbieranie drewna z mygieł na danym obszarze.
- Główny czujnik to **mikrofon**. Akcelerometr zostaje jako zapasowy: pozwala na głęboki sen i może się okazać skuteczniejszy.
- Algorytm detekcji działa **na urządzeniu**. Wysyłamy tylko wynik, a transmisję ograniczamy do minimum.
- Komunikacja **jednostronna** (urządzenie → serwer).
- GPS jest w terminalu leśniczego, nie w urządzeniu.
- Wydanie drewna: leśniczy przekazuje przewoźnikowi określoną liczbę kłód, potwierdza to w terminalu i w naszej aplikacji, potem odjeżdża.
- Firmware: najpierw proof of concept w Pythonie, docelowo C. Oszczędzanie energii przez deep sleep i wybudzanie komponentów.
- Łączność: z satelity zrezygnowaliśmy. Do wyboru zostały **LoRa i NB-IoT**.
- Jeden prototyp. Na pierwszy prototyp bateria nie jest problemem.
- Język projektu: polski.

### Największe wyzwania
- Oszczędzanie energii: dwa procesory, mikrofon jako trigger wybudzający radio.


### Rozważany sprzęt
- Moduł z mikrofonem elektretowym i wzmacniaczem OPA344 - SparkFun
- SparkFun MPU-9250 9DoF - 3-osiowy akcelerometr, żyroskop i magnetometr I2C
- LoPy (ESP32 + LoRa, WiFi, BLE, API w Pythonie) z płytką Pycom Expansion Board v2

## Zespół

| Obszar | Osoba | Zakres |
|---|---|---|
| Project Manager | Tymon | harmonogram, kontakt z prowadzącym, integracja |
| Hardware | Wojtek | czujniki, PCB, obudowa |
| Embedded | Damian | firmware, obsługa czujników, energooszczędna transmisja |
| Connectivity | Martyna | wybór i obsługa łączności |
| Data Analyst | Kiryl | algorytm detekcji |
| Backend | Kacper | serwer, baza danych, API |
| Frontend | Agata | aplikacja z powiadomieniami push |

## Struktura repo

| Katalog | Zawartość |
|---|---|
| `backend/` | serwer (Python, Docker) |
| `frontend/` | aplikacja dla leśniczego |
| `firmware/` | oprogramowanie mikrokontrolera |
| `hardware/` | PCB, obudowa |
| `comms/` | łączność |
| `detection/` | algorytm detekcji, dane, notebooki |
| `docs/` | dokumentacja, notatki ze spotkań (`docs/meetings/`) |

Zasady pracy z repo opisuje [CONTRIBUTING.md](CONTRIBUTING.md).

## Linki

- [Lista urządzeń (UPeL)](https://upel.agh.edu.pl/mod/folder/view.php?id=453953)
- [Excel z podziałem](https://aghedupl-my.sharepoint.com/:x:/g/personal/kks_agh_edu_pl/IQCxSIKTbemgRo97P_-m8VCBAS5CAIudH66-dRaOSBrDc34?e=VrRsyi)
- [Karta projektu](https://aghedupl-my.sharepoint.com/:w:/g/personal/twozniak_student_agh_edu_pl/IQAcMxB2Ik2qTo55fBwVSHiMAbE1DVx7Ct5AAJeqKGnZN2o?e=MPKtkL)
- [Lista grup](https://docs.google.com/spreadsheets/d/11RTGv6CSY3fC4iVpIKA_a65sy7gYM6XlGd3oxX1Dz3g/edit?gid=0#gid=0)
