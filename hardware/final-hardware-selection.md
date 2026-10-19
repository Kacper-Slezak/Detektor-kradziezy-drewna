# Hardware

Poniższy dokument zawiera ostateczny zestaw wybranych komponentów do wykonania projektu

---

## MCU
**moduł LoPy ESP32 (moduł LoRa, WiFi, Bluetooth BLE + Python API) z Pycom Expansion Board v2**

Opis produktu: https://botland.com.pl/produkty-wycofane/7873-lopy-esp32-modul-lora-wifi-bluetooth-ble-python-api-700461341628.html
Dodatkowo dostępny jest Expansion Board: https://docs.pycom.io/datasheets/expansionboards/expansion2/ -> ułatwi to podłączenie

![image](https://cdn1.botland.com.pl/img/art/inne/07873_3.jpg)

### Główne cechy urządzenia:
- Napięcie pracy: od 3,3 V do 5,5 V
- Mikrokontroler: ESP32
- Pamięć RAM: 512 kB
- Pamięć Flash: 4 MB
- Wbudowany moduł WiFi 802.11b/g/n o zasięgu do 1 km
- Wbudowany stos IP v6
- Moduł dalekiego zasięgu LoRa (Long Range)
- Częstotliwość: 868 MHz (Europa) - moc do +14 dBm
- 915 MHz (Ameryki, Australia i Nowa Zelandia) - moc do +20 dBm
- Zasięg: Tryb Node: do 40 km
- Tryb Nano Gateway: do 22 km (pojemność do 100 nodów)
- Wbudowany moduł Bluetooth BLE 4.2
- Wbudowany zegar czasu rzeczywistego RTC 32 kHz
- Wbudowany kontroler DMA
- Linie GPIO: 24 wyprowadzeń
- Interfejsy komunikacyjne: 2x UART, 2x SPI, I2C, I2S, SD Card
- Wbudowany przetwornik analogowo-cyfrowy,: 8 kanałowów o rozdzielczości 12 bitów
- Liczniki z czterema, 16-bitowymi wyjściami PWM
- Dioda LED RGB WS2812
- Zabezpieczenia WiFi: SSL/ TLS, WPA
- Konektor u.FL do podłączenia zewnętrznej anteny
- Wymiary: 55 x 20 x 3,5 mm

### Dokumentacja i materiały
- [Informacje na stronie producenta](https://docs.pycom.io/datasheets/development/lopy/)
- [Specyfikacja techniczna](./assets/lopySpecsheetFinal.pdf)
- [Obsługa ESP32 w Arduino IDE](https://www.dfrobot.com/blog-598.html)
- [Tutorial MicroPython](https://www.dfrobot.com/blog-692.html?tracking=59cf43642c1e8&utm_source=DFRobot_Newsletter&utm_campaign=829f546aa4-EMAIL_CAMPAIGN_2017_National&utm_medium=email&utm_term=0_0633b8d2f9-829f546aa4-19754189)
- [Wiele przykładów z ESP32](https://www.dfrobot.com/blog-tag-esp32.html)

---

## Czujnik wibracji
**Czujnik wibracji z membraną piezzoelektryczną - DFRobot Gravity**

Opis produktu: https://botland.com.pl/gravity-czujniki-sily-i-krancowki/4713-dfrobot-gravity-czujnik-wibracji-z-membrana-piezoelektryczna-6959420901029.html#product_tab_description

**Analogowy** czujnik wibracji z piezoelektryczną membraną. Zasilany jest napięciem od 3,3 V do 5 V, współpracuje z modułami Arduino.
Na wyjściu modułu można odczytać zmiany napięcia proporcjonalne do siły wibracji.

<img src="https://cdn1.botland.com.pl/img/art/inne/04713_5.jpg" height="200">

### Specyfikacja
| Nazwa | Wartość |
|---|---|
| Napięcie zasil. od | 3.3 V |
| Napięcie zasil. do | 5.0 V |
| Moduł - typ | Wibracji |
| Moduł - montaż | Na przewody |
| Szerokość | 5,5 cm |
| Wysokość | 6 cm |
| Głębokość | 2,5 cm |
| Waga | 0,03 kg |

### Materiały i dokumentacja
- [Strona producenta DFRobot DFR0052](https://www.dfrobot.com/product-399.html#.VhI1OiuG2Hs)
- [Przewodnik użytkownika WikiDoc](https://wiki.dfrobot.com/dfr0052/)
- [Schemat modułu](https://dfimg.dfrobot.com/wiki/17157/DFR0052_digital-piezo-disk-vibration-sensor_schematics_v1.0.pdf)
- [Dokumentacja techniczna](https://dfimg.dfrobot.com/wiki/17157/DFR0052_digital-piezo-disk-vibration-sensor_datasheet_v1.0.pdf)

---

## Mikrofon
**Moduł z mikrofonem elektretowym i wzmacniaczem OPA344 - SparkFun**

Opis produktu: https://botland.com.pl/mikrofony-i-detektory-dzwieku/1614-modul-z-mikrofonem-elektretowym-i-wzmacniaczem-opa344-sparkfun-bob-12758-5904422300722.html

Moduł z mikrofonem elektretowym i wzmacniaczem operacyjnym. Dzięki zastosowanemu układowi op-amp (OPA344), sygnał napięciowy pochodzący z mikrofonu wzmacniany jest 100-krotnie. Pozwala to na bezpośrednie podłączenie modułu do pinów wejściowych przetwornika analogowo-cyfrowego (np. wejść analogowych Arduino). Układ zasilany jest napięciem z zakresu od 2,7 V do 5,5 V.


<img src="https://cdn2.botland.com.pl/26875-large_default/modul-z-mikrofonem-elektretowym-i-wzmacniaczem-opa344-sparkfun-bob-12758.jpg" height="200">

### Specyfikacja techniczna:
- Napięcie zasilania: od 2,7 V do 5,5 V
- Pobór prądu: maks 0,5 mA
- Zakres częstotliwości: od 100 Hz do 10 000 Hz
- Wymiary modułu: 17 x 11 x 8 mm

### Dokumentacja i materiały
- [Strona producenta: SparkFun BOB-12758](https://www.sparkfun.com/sparkfun-electret-microphone-breakout.html)
- [Schemat modułu](https://cdn.sparkfun.com/datasheets/BreakoutBoards/Electret_Microphone_Breakout_v20.pdf)
- [Pliki programu Eagle](https://cdn.sparkfun.com/datasheets/BreakoutBoards/Electret_Microphone_Breakout_v20.zip)
- [Przewodnik użytkownika](https://learn.sparkfun.com/tutorials/electret-mic-breakout-board-hookup-guide?_ga=1.94255261.1456259301.1473232006)
- [Pliki w systemie GitHub](https://github.com/sparkfun/Electret_Microphone_Breakout/tree/Revision)
- [Dokumentacja wzmacniacza operacyjnego OPA344](https://botland.com.pl/index.php?controller=attachment&id_attachment=340)
- [Dokumentacja mikrofonu](https://botland.com.pl/index.php?controller=attachment&id_attachment=339)

---

## Pozostałe komponenty układu

### Akumulator Li-ion 18650
Wybrany został akumulator bez BMS ze względu na specyfikę urządzenia oraz fakt, że w urządzeniu będą wymieniane akumulatory.

2x [Akumulator Samsung 35E INR18650-35E 3500mAh Li-Ion 3.6V](
https://allegro.pl/events/clicks?emission_unit_id=76c621c1-4cf8-41bd-85a8-806af5e4db70&emission_id=20c9b42c-4e3a-48f3-9190-c46e5c0091c3&type=OFFER&ts=1792414665473&redirect=https%3A%2F%2Fallegro.pl%2Foferta%2F18813433448%3Fbi_s%3Dads%26bi_m%3Dproductlisting%253Adesktop%253Aquery%26bi_c%3DYmExZDU1YmMtZWU5MC00NDc4LWJiYjYtMTY4N2QyOWNmNWIyAA%26bi_t%3Dape&placement=productlisting:desktop:query&sig=7822ad27035cf816447d7c023e1e1dff)



### Moduł BMS
[Moduł BMS PCM PCB Ładowania i Ochrony Ogniw Li-ion 2S 8,4V 8A do 18650](https://allegro.pl/produkt/ladowarka-abc-8355-11145404-07e3-490f-920e-0e06216b4d84?offerId=18299673018)

Moduł obsługuje dwa akumulatory

## Przetwornica impulsowa typu step-down
[Przetwornica LM2596 DC-DC Step-Down 3A 3-35V na 1,5-30V do FPV do Projektów](https://allegro.pl/produkt/przetwornica-abc-rc-lm2596-1e9aba40-4602-428a-b5be-f7c754625060?offerId=18660363316)

> [!WARNING]  
> Przetwornica LM2596 nie jest obojętna dla zużycia energii. W zastosowaniu komercyjnym powinna zostać użyta inna przetwornica, ale do prototypu ten model jest tańszy i bardziej dostępny


### Koszyk do baterii
[Koszyk na Akumulator 2x 18650 z Wyłącznikiem Koszyczek z Pokrywą Przewodami](https://allegro.pl/produkt/koszyk-na-akumulator-18650-abc-2-szt-z-wylacznikiem-i-pokrywa-ad0608e5-a5b0-45b5-b293-2add310675f1?offerId=18518318930)
