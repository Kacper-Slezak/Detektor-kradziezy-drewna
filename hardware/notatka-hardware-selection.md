# Notatka dotycząca wyboru sprzętu

**Cel notatki:** propozycja doboru płytki wraz z odpowiednimi czujnikami

---

## Propozycje płytek MCU
Ogólnie najlepsze byłoby do prototypu nRF9151, ponieważ zawiera modem NB-IoT oraz GNSS, ale cena nie jest akceptowalna.


| MCU | Mocne strony | Słabe strony | Wnioski |
|---|---|---|---|
| ESP32-S3 | tanie, duża społeczność, łatwość programowania | Wyższy pobór energii; Wi‑Fi jest zbędne; trudniej uzyskać wieloletnie zasilanie bateryjne; pobór mocno zależy od konkretnej płytki | Dobry do szybkiego demo, słabszy do finalnego czujnika bateryjnego |
| XIAO nRF52840 | Bardzo niski pobór, Cortex-M4F, sprzętowy PDM/I²S, ADC, UART, I²C/SPI, mała płytka | Mniejsza społeczność niż ESP32; ograniczona liczba pinów w standardowym XIAO | chyba tez dobry wybor |
| XIAO nRF52840 Plus | j.w. ale wiecej pinow | 
| STM32U585 | Bardzo niski pobór, wysoka wydajność | Droższa płytka, mega ciezko dostepna | raczej nie do prototypu |
| RP2040 | Tani, prosty, dużo przykładów | Słabsze tryby niskiego poboru, brak natywnego PDM, mniejsza przydatność do wieloletniej pracy | Raczej nie w tym projekcie |

---

## Moduł NB-IoT


https://botland.com.pl/raspberry-pi-hat-komunikacja/14779-nb-iot-hat-sim7020e-nakladka-dla-raspberry-pi-4b3b3b2bzero-waveshare-15936-5904422322533.html \
https://botland.com.pl/moduly-unit-moduly-komunikacyjne/25329-nb-iot-2-modul-komunikacyjny-cat-nb-z-antena-sim7028-modul-rozszerzen-unit-m5stack-u111-b-6972934175335.html



---

### Czujniki
- Akcelerometr 3-osiowy - wykrywa wibracje, uderzenia, załadunek lub zmianę kąta nachylenia kłody.


  | Model | Pobór prądu (Aktywny - typowy) | Pobór prądu (Wake-up / Uśpienie) | Rozdzielczość | Zakresy pomiarowe | Główne zalety / Wbudowane funkcje |
  | --- | --- | --- | --- | --- | --- |
  | ADXL362 | ~2 µA (przy 100 Hz) | 270 nA (Wake-up) / 10 nA (Off) | 12-bit | "±2, 4, 8 g" | "Absolutny lider oszczędzania energii, dosyć drogie i trudno dostępne." |
  | **LIS2DW12** | < 1 µA (Low-power) do 90 µA | 50 nA (Power-down) | 16-bit | "±2, 4, 8, 16 g" | "Świetny stosunek ceny do możliwości, bardzo niski szum | wysoka rozdzielczość."
  | **IIS2DLPC** | < 1 µA (Low-power) do 90 µA | 50 nA (Power-down) | 14-bit | "±2, 4, 8, 16 g" | "Wersja o podwyższonej niezawodności (Industrial) to samo co powyzej, wysoka odporność na wstrząsy, do masowej produkcji tańsze"
  | BMA400 | ~2.8 µA (przy 125 Hz) | < 1 µA (Auto-wakeup) | 12-bit | "±2, 4, 8, 16 g" | "Zoptymalizowany pod ""always-on"" |  wbudowany sprzętowy krokomierz (tylko 4 µA)."
  ICM‑42670‑P | ~550 µA (Low-Noise) | 3.5 µA (Sleep) | 16-bit | "±2, 4, 8, 16 g" | 6-osiowy IMU (Akcelerometr + Żyroskop). Posiada sprzętowy procesor ruchu (APEX).

  Akcelerometr będzie wybudzał nasze MCU. Najlepszym wyborem jest chyba IIS2DLPC lub LIS2DW12 (w zależności od dostępności). ADXL362 pobiera najmniej energii ale koszt zakupu jest bardzo drogi.

- Mikrofon \
  Zakładamy że mikrofon dokonuje nagrywania dźwięku dopiero po wybudzeniu MCU, które nastąpiło po wykryciu drgań.

  | Mikrofon | Interfejs | Pobór aktywny | Zalety | Wady |
  |---|---|---|---|---|
  | M5Stack SPM1423PDM | PDM | Około 600 µA | Prosty moduł, dogodny do prototypu, cyfrowy sygnał | Duża płytka, wymaga obsługi PDM, złącze Grove |
  | Adafruit SPH0645 | I²S | Około 600 µA | Standardowe próbki I²S, dobra dokumentacja | Sam mikrofon wycofany z produkcji |

  https://kamami.pl/moduly-peryferyjne/582027-m5stack-pdm-mini-unit-modul-z-mikrofonem-mems-spm1423-u089-5906623409051.html

  https://botland.com.pl/mikrofony-i-detektory-dzwieku/9715-sph0645lm4h-mikrofon-mems-i2s-adafruit-3421-5904422307103.html

- Kontaktron (czujnik magnetyczny), do ustalenia
  W zaleznosci od tego czy chcemy wykryć przerwanie pętli
  

- Odbiornik GPS/GNSS -> można robić tak, że korzystamy z cell id i jak sie zmieni to wtedy GPS???

----

## 
Mikrokontroler powinien przez wiekszosc czasu byc w stanie **Deep Sleep** lub **Standby / Hibernate**.
NB-IoT całkowicie odciete od zasilania, GNSS tak samo (gdyby byl uzyty)




