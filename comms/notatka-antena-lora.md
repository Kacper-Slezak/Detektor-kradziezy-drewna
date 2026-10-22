## Wybór anteny LoRa – węzeł (LoPy)

**Wybrana antena:** Nettigo „Antena 868 MHz do modułów LoRa” (kod AKC-1424), ok. 9,90 zł brutto
Link: https://nettigo.pl/products/antena-868-mhz-do-modulow-lora

### Parametry
| Parametr | Wartość |
|---|---|
| Pasmo | 868–915 MHz (obejmuje EU868) |
| Zysk | 2 dBi |
| VSWR | ≤ 1,5 (pomiar sklepu przy 868 MHz: 1,23–1,5) |
| Impedancja | 50 Ω |
| Charakterystyka | dookólna, polaryzacja pionowa |
| Złącze | antena SMA męskie + pigtail 16 cm SMA żeńskie → u.FL (IPEX-1) w zestawie |
| Wymiary / masa | 8 × 50 mm, 9 g |
| Temperatura pracy | −40 … +85 °C |

### Dlaczego ta antena
- **Pasuje bezpośrednio do LoPy:** LoPy nie ma wbudowanej anteny LoRa, tylko gniazdo u.FL. Pigtail u.FL jest w zestawie, więc nie trzeba dokupować przejściówki.
- **Właściwe pasmo:** 868 MHz, czyli europejskie pasmo LoRaWAN (EU868).
- **Sprawdzone dopasowanie:** VSWR zmierzony przez sprzedawcę, a nie tylko deklarowany.
- **Mały rozmiar (5 cm):** łatwiej ukryć w stosie drewna niż antenę 17–30 cm.
- **Zgodność z limitem mocy w UE (25 mW ERP ≈ 16 dBm EIRP):** przy zysku 2 dBi można nadawać z mocą ok. 14 dBm. Przy antenach 3–5 dBi trzeba by zejść do 11–13 dBm, więc przewaga większych anten w zasięgu praktycznie znika.
- **Odporność na mróz** (do −40 °C) i dostępność w Polsce (szybka dostawa).

### Rozważane alternatywy
| Antena | Zysk | Rozmiar | Dlaczego nie (dla węzła) |
|---|---|---|---|
| Hongsense 868 MHz, magnetyczna (Maritex) | 5 dBi | ok. 30 cm | duża, potrzebna osobna przejściówka u.FL→SMA, trzeba obniżyć moc do ok. 11 dBm |
| Antena prętowa 868 MHz z kablem IPEX-1 (AliExpress) | 3 dBi | 17 cm + kabel 20 cm | parametry tylko deklarowane, większa, dłuższa dostawa. **Dobra opcja dla bramki.** |

Antena z Maritex była omawiana w trkacie spotkania z Panem Krzysztofem Grochotem

Linki do anten:
- https://www.maritex.eu/produkt/hongsense-868mhz-magnetic-base-1.m-cable-sma-male-anteny-rf-ant15ss-868?utm_source=google&utm_medium=cpc&utm_campaign=23031604774&utm_term=&utm_content=&cmc_adid=ga__23031604774&gad_source=1&gad_campaignid=23291453196&gbraid=0AAAAAD2KTFNqkor-P9wAdCjzHphEqAY0z&gclid=CjwKCAjw0LzWBhBOEiwAKQd0cAZv7vmCWExNSpC-zMknG577Jdsklu42-R1Uk07q_7SMRFVm0tgfahoCymIQAvD_BwE
- https://pl.aliexpress.com/item/1005005275069992.html?src=google&src=google&albch=shopping&acnt=708-803-3821&isdl=y&slnk=&plac=&mtctp=&albbt=Google_7_shopping&aff_platform=google&aff_short_key=UneMJZVf&gclsrc=aw.ds&albagn=888888&ds_e_adid=&ds_e_matchtype=&ds_e_device=t&ds_e_network=x&ds_e_product_group_id=&ds_e_product_id=pl1005005275069992&ds_e_product_merchant_id=109215665&ds_e_product_country=PL&ds_e_product_language=pl&ds_e_product_channel=online&ds_e_product_store_id=&ds_url_v=2&albcp=15838179320&albag=&isSmbAutoCall=false&needSmbHouyi=false&gad_source=1&gad_campaignid=15829774284&gbraid=0AAAAAD6I-hFX2fSOQPHM8GACrF0SGFGzO&gclid=CjwKCAjw3NHWBhANEiwAtpwId-fGTvHlnX_PRcS8P_A21SiwpD2NxtwnQaNrsk4rH5qJeYa5Z66WihoCc2EQAvD_BwE

### Uwagi do montażu i użycia
- Pigtail wpinamy w gniazdo **LoRa 868 MHz** (LoPy4: prawe gniazdo u.FL przy diodzie), nie w gniazdo WiFi.
- **Nie uruchamiamy LoRa bez podłączonej anteny**, bo grozi to uszkodzeniem modułu (ostrzeżenie Pycom).
- Antena ustawiona **pionowo**, tak samo jak antena bramki.
- W kodzie moc nadawania ok. **14 dBm**.
- Dla bramki warto użyć większej anteny (3–5 dBi) ustawionej jak najwyżej, bo to najbardziej poprawia zasięg łącza.

### Źródła
- Nettigo – karta produktu: https://nettigo.pl/products/antena-868-mhz-do-modulow-lora
- Pycom – podłączenie LoPy4 (gniazda u.FL, ostrzeżenie o antenie): https://development-test.pycom.io/getting-started/connection/lopy4
- The Things Network – EU868 (limit mocy 25 mW ERP): https://www.thethingsnetwork.org/docs/lorawan/regional-parameters/eu868/
- Compex Flatant – karta katalogowa (pasma 2,4/5 GHz): https://static6.arrow.com/aropdfconversion/fb42649d77196a0ba9bb44785ea2e92b94ef1044/flatant-3x3-v1.3-wh-213.pdf