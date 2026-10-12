# Notatka dotycząca technik przesyłu danych

**Cel notatki:** wybór łączności dla węzła ukrytego w mygle przy drodze leśnej.

**Wymagania:** ok. 6 wiadomości na dobę, ramki 6-20 B, potrzebny kanał zwrotny (komendy z serwera), zasilanie bateryjne przez kilka lat, praca w lesie przy słabym zasięgu.

## Spis treści

- [Techniki wzięte pod uwagę](#techniki-wzięte-pod-uwagę)
- [Parametry technik](#parametry-technik)
- [Porównanie różnych technik](#porównanie-różnych-technik)
- [Satelity – specyfikacje i różnice (Iridium i Skylo)](#satelity--specyfikacje-i-różnice-iridium-i-skylo)
- [Plusy każdej z technik](#plusy-każdej-z-technik)
- [Minusy każdej z technik](#minusy-każdej-z-technik)
- [Zasięg sieci komórkowej w lesie](#zasięg-sieci-komórkowej-w-lesie)
- [Energia (wstępne rozeznanie)](#energia-wstępne-rozeznanie)
- [Ważny aspekt dotyczący NB-IoT/LTE-M przy PSM](#ważny-aspekt-dotyczący-nb-iotlte-m-przy-psm)
- [Koszty w Polsce za każdą z technik](#koszty-w-polsce-za-każdą-z-technik)
- [Obliczenia dotyczące ruchu danych](#obliczenia-dotyczące-ruchu-danych)
- [Dodatkowy pomysł: śledzenie ciężarówki](#dodatkowy-pomysł-śledzenie-ciężarówki)
- [Linki i źródła](#linki-i-źródła)

---

## Techniki wzięte pod uwagę

1. **LoRaWAN** – protokół komunikacyjny i architektura sieci typu LPWAN, przeznaczone przede wszystkim do komunikacji urządzeń Internetu rzeczy. LoRaWAN wykorzystuje LoRa jako warstwę fizyczną łącza radiowego.
2. **LTE-M** – komórkowa technologia LPWA zbudowana na istniejącej strukturze 4G LTE, która obsługuje wyższe prędkości transmisji danych, mobilność i funkcje głosowe (VoLTE) przy jednoczesnym zachowaniu niskiego zużycia energii. Działa z przepustowością 1,4 MHz i umożliwia urządzeniom pozostanie w kontakcie podczas przemieszczania się między komórkami, dzięki czemu nadaje się do zastosowań wymagających stałej łączności i częstej wymiany danych.
3. **NB-IoT** – koncentruje się na bardzo niskim zużyciu energii i doskonałym zasięgu, zwłaszcza w pomieszczeniach i pod ziemią, wykorzystując wąskie pasmo 180-200 kHz. Jest to idealne rozwiązanie dla urządzeń stacjonarnych, które rzadko wysyłają niewielkie ilości danych, takich jak liczniki mediów i czujniki środowiskowe. Żywotność baterii może przekraczać 10 lat w wielu wdrożeniach ze względu na wydajność technologii.
4. **Łączność satelitarna** – satelitarny IoT łączy urządzenia bezpośrednio z satelitami, omijając wieże naziemne. Dzięki temu idealnie nadaje się do odległych obszarów, operacji morskich i infrastruktury krytycznej.
5. **LTE** – standard bezprzewodowego przesyłu danych będący następcą systemów trzeciej generacji, rozwijany przez konsorcjum 3GPP. Głównymi celami nowego standardu jest zwiększenie możliwości telefonii komórkowej poprzez zwiększenie prędkości przesyłania danych, zmniejszenie opóźnień, zwiększenie efektywności spektralnej łączy radiowych, zmniejszenie kosztów transmisji danych, uproszczenie architektury.

---

## Parametry technik

### 1. LoRaWAN

- **Główne pasmo:** 868 MHz (dokładnie podzakres EU863-870 MHz). Jest to standardowe, najpopularniejsze pasmo dla urządzeń LoRaWAN w Europie.
- **Alternatywne pasmo:** 433 MHz (podzakres ISM) – rzadziej stosowane, ale również dopuszczone do użytku w nielicencjonowanych aplikacjach radiowych.
- **Limity mocy:** urządzenia w paśmie 868 MHz muszą mieścić się w określonych limitach mocy (zazwyczaj maksymalnie 25 mW ERP dla wielu podzakresów) oraz spełniać normy Duty Cycle (procentowy limit czasu nadawania), aby nie zakłócać innych systemów (np. stacji pogodowych czy automatyki domowej).

### 2. LTE-M

Źródło: <https://orange-m2m.pl/lte-m.html>

- Technologia **LTE-M (Cat-M1)** w Polsce jest wykorzystywana głównie przez sieć Orange (która pokrywa nią niemal cały kraj), korzystając z pasm:
  - **800 MHz (Band 20)** – główne, ogólnopolskie pasmo pokryciowe o dużym zasięgu i dobrej przenikalności.
  - **1800 MHz (Band 3)** – pasmo używane lokalnie, głównie do zwiększenia pojemności sieci.

### 3. NB-IoT

- Głównie **LTE 800 MHz (Band 20)** dla optymalnego zasięgu w budynkach i podziemiach, a także **900 MHz (Band 8)** oraz **1800 MHz (Band 3)**.
- Pojedynczy blok ma **180 kHz** (zapasowo rozszerzany do 200 kHz z pasmem ochronnym).
- Operatorzy:
  - **T-Mobile Polska** – oferuje ogólnopolski zasięg NB-IoT bazujący na stacjach bazowych LTE 800 MHz.
  - **Plus** – oferuje NB-IoT dla biznesu w ramach licencjonowanego pasma z obsługą prywatnego APN.
  - **Orange** – również wykorzystuje infrastrukturę częstotliwości LTE dla rozwiązań M2M / IoT (często we współpracy z T-Mobile w ramach NetWorkS!).

### 4. Łączność satelitarna

Pasmem nazywamy fragment widma fal elektromagnetycznych. W łączności satelitarnej wykorzystywane są mikrofale w różnych zakresach częstotliwości. Spowodowane jest to różnymi charakterystycznymi cechami danych pasm (m.in. odporność na warunki atmosferyczne, moc itp.).

| Nazwa pasma | Zakres częstotliwości [GHz] | Zastosowanie |
|---|---|---|
| Pasmo L | 1 - 2 | Telekomunikacja, cyfrowe radio DAB (World Space) [1452 - 1492 MHz] |
| Pasmo S | 2 - 3 | Telekomunikacja, radary, cyfrowe radio DAB (Sirius / XM) |
| Pasmo C | 3.4 - 4.2 | Transmisje telewizyjne i radiowe |
| Pasmo K<sub>u</sub> | 10.7 - 12.75 | Transmisje telewizyjne, radiowe, przesył danych (np. internet) |
| Pasmo K<sub>a</sub> | 18 - 22 | Transmisje telewizyjne, radiowe, przesył danych (np. internet) |

### 5. LTE

**Główne pasma LTE w Polsce:**

| Pasmo | Zasięg | Prędkość | Zastosowanie |
|---|---|---|---|
| **LTE 800 MHz (Band 20)** | Bardzo duży, świetnie przenika przez ściany (idealne na tereny wiejskie i do wnętrz budynków) | Niska, mniejsza przepustowość | – |
| **LTE 900 MHz (Band 8)** | Duży, stosowany pomocniczo na obszarach mniej zurbanizowanych lub jako refarming po GSM | Niska lub średnia | – |
| **LTE 1800 MHz (Band 3)** | Dobrze zbalansowany | Dobrze zbalansowana | Podstawowy i najpopularniejszy filar sieci LTE w miastach oraz na wsiach |
| **LTE 2100 MHz (Band 1)** | Średni | Średnia | Często wdrażane w ramach refarmingu dawnych częstotliwości 3G do obsługi większej liczby użytkowników w miastach |
| **LTE 2600 MHz (Band 7 / TDD Band 38)** | Mały, krótki promień działania | Najwyższa (duża szerokość kanału) | Centra dużych miast i miejsca o dużym natężeniu ruchu danych (tzw. pasmo pojemnościowe) |

- Większość nowoczesnych telefonów i routerów w Polsce łączy kilka pasm jednocześnie (np. Band 3 + Band 7 + Band 20), co pozwala znacznie zwiększyć prędkość pobierania danych.
- LTE też działa na 800 MHz. Główny problem polega na tym, że LTE nie ma trybów wzmacniania zasięgu, które mają NB-IoT i LTE-M. Fale są przez drewno i liście głównie tłumione (pochłaniane i rozpraszane), a nie „odbijane”.

---

## Porównanie różnych technik

| Network | Sigfox | LoRa | NB-IoT (Cat NB1) | LTE-M (Cat M1) |
|---|---|---|---|---|
| Type | PLWAN | PLWAN | DSSS modulation | LTE (cellular) |
| Low Power | +++++ | ++++ | ++++ | +++ |
| Throughput Kbit/s | 0,1 | 50 | 100 | 375 |
| Bandwidth | Ultra-narrowband | Narrowband | Narrowband | Low |
| Latency | 1 – 30 s | Based on profile | 1.6 – 10 s | 10 – 15 ms |
| Standard | Proprietary | Proprietary | 3GPP Rel. 13 | 3GPP Rel. 13 |
| Availability world-wide | ++ | +++ | ++ | ++ |
| Spectrum | Unlicensed ISM | Unlicensed ISM | Licensed LTE | Licensed LTE |
| Complexity | Very low | Low | Very low | Low / medium |
| Coverage / range | Medium / high | Medium / high | High | High |
| Battery life | Very high | Very high / high | High | Medium / high |
| Gateway needed | Yes | Yes | No, but optional | Optional |
| Signal penetration | High | Medium / high | Medium / high | Medium / high |
| Security | +++ | +++ | +++ | +++++ |
| Future proof | +++ | +++ | +++++ | +++++ |

---

## Satelity – specyfikacje i różnice (Iridium i Skylo)

| | **Iridium** | **Skylo** |
|---|---|---|
| **Czym jest?** | Własna konstelacja satelitów | Operator sieci, ale bez własnych satelitów. Ma własną sieć radiową i rdzeń w standardzie 3GPP, zainstalowane w stacjach naziemnych, i dzierżawi pojemność na cudzych satelitach geostacjonarnych (m.in. Inmarsat). |
| **Orbita** | Niska (LEO): 66 satelitów na wysokości 780 km, 6 płaszczyzn biegunowych, nachylenie 86,4°, jedno okrążenie trwa 101 min | Geostacjonarna (GEO), ok. 36 000 km. Satelita stoi w jednym miejscu na niebie. |
| **Pasmo** | L-band, 1616-1626,5 MHz. Satelity łączą się między sobą w paśmie Ka, więc wiadomość płynie „po niebie” i nie potrzebuje stacji naziemnej w pobliżu. | NB-IoT w wersji satelitarnej (3GPP Rel-17), pasma B255 (L) i B256 (S) |
| **Gdzie jest na niebie (Polska)** | Przelatuje nad głową. Od horyzontu do horyzontu w niecałe 10 minut. | Nisko nad południowym horyzontem. Ok. 30° (wyliczenie własne dla Warszawy i satelity na 25°E). |
| **Wiadomość** | SBD: do 340 B w górę, 270 B w dół. Przy czystym niebie ok. jedna sesja na 10 s. | Małe pakiety. Przez Blues rozliczane jako minimum 50 B. |
| **Moduł** | 9603N: szczytowy pobór 1,3 A, średnio ok. 158 mA na sesję | Moduł z certyfikatem Skylo, często razem z NB-IoT/LTE-M (np. Quectel BG95-S5, CC660D-LS). Moduł musi znać swoją pozycję GNSS. |
| **Antena** | Polaryzacja kołowa prawoskrętna (RHCP), np. ceramiczny patch 25×25 mm | Antena L/S-band. Często jedno złącze na sieć komórkową i satelitę. |
| **Dostępność w Europie** | Globalnie, także bieguny | Skylo deklaruje komercyjny zasięg m.in. w Europie. W Europie oferują go Deutsche Telekom, Vodafone IoT i Telefónica Niemcy. |
| **Odbiór komend (downlink)** | Wiadomość czeka na urządzenie w „skrzynce”. Urządzenie musi się samo połączyć, a każde sprawdzenie skrzynki, także pustej, kosztuje kredyt. | Jak w NB-IoT: urządzenie odbiera, gdy samo się zgłosi |

> **Co to oznacza dla mygły:** Iridium poradzi sobie z wąskim pasem nieba nad drogą, bo satelity przelatują w różnych kierunkach i wystarczy ponawiać próby. Skylo potrzebuje prześwitu w stronę południa. Dla obu antena musi wyjść ze stosu.

---

## Plusy każdej z technik

### 1. LoRaWAN (z własną bramą)

- (+) jeden z najoszczędniejszych energetycznie węzłów
- (+) małe pakiety
- (+) brak abonamentu za każdy czujnik
- (+) zasięg w otwartym terenie może wynosić do 15 km, ale w gęstym lesie zdecydowanie spadnie (pomiary z [artykułu MDPI](https://www.mdpi.com/1999-5903/13/5/115) pokazują ok. 860 m w gęstym lesie i ok. 2 km w rzadszym)

Działa tam, gdzie w ogóle nie ma zasięgu komórkowego, bo wystarczy, że brama ma łączność, np. na skraju lasu albo na wzniesieniu.

### 2. LTE-M

- (+) obsługuje przełączanie między stacjami bazowymi w locie
- (+) możliwość śledzenia ciężarówki wywożącej skradzione drewno w czasie rzeczywistym, to wtedy LTE-M jest znacznie lepsze niż NB-IoT (może to nie byłby głupi pomysł szczerze ????)
- (+) niski czas opóźnień

**Tabela porównująca LTE-M oraz NB-IoT:**

| Cecha | LTE-M | NB-IoT |
|---|---|---|
| Szybkość transmisji danych | Wyższa (do ~1 Mb/s) | Niższa (do ~250 kbps) |
| Mobilność | Pełna obsługa | Tylko statyczne |
| Wydajność energetyczna | Wysoka | Bardzo wysoka |
| Głębokość pokrycia | Dobra | Doskonała |
| Opóźnienie | Niskie | Wyższe |
| Głos (VoLTE) | Tak | Nie |
| Koszt modułu | Średni | Niski |
| Najlepsze dla | Mobilne i umiarkowana ilość danych | Statyczne i mało danych |

### 3. NB-IoT

- (+) bardzo dobrze radzi sobie z tłumieniem przez mokre drewno i gęsty las
- (+) bardzo mały pobór prądu dzięki trybowi PSM
- (+) tanie moduły i karty SIM
- (+) niskie pasmo dobrze sprawdza się w lesie

### 4. LTE

- (+) największy zasięg terytorialny sieci
- (+) najprostsza integracja
- (+) wysoka przepustowość

### 5. Satelita

- (+) działa wszędzie, gdzie widać niebo
- (+) działa wszędzie tam, gdzie nie ma zasięgu komórkowego

---

## Minusy każdej z technik

### 1. LoRaWAN

- (−) trzeba postawić i zasilić bramę, a sama brama też może zostać ukradziona lub zniszczona
- (−) w Europie obowiązuje limit czasu nadawania (duty cycle), a downlink jest możliwy tylko zaraz po uplinku (klasa A)
- (−) gęsty las, ukształtowanie terenu i położenie anten mogą ograniczać zasięg
- (−) są limity czasu nadawania i ograniczenia odbioru danych w dół zależne od pasma oraz konfiguracji

### 2. LTE-M

- (−) dostępność w Polsce trzeba sprawdzić: sprzedawca kart IoT pisze, że LTE-M jest dostępne tylko w części miejsc → dostępność zależy od operatora, konkretnej sieci i obsługiwanych pasm
- (−) nadal wymaga zasięgu infrastruktury naziemnej
- (−) koszt i czas rejestracji modemu w sieci mogą dominować nad kosztem przesyłania kilku bajtów
- (−) radzi sobie nieco gorzej z przeszkodami
- (−) zużywa minimalnie więcej prądu przy wybudzaniu niż NB-IoT

### 3. NB-IoT

- (−) wymaga pokrycia sieci (choć operatorzy inwestują w NB-IoT na terenach wiejskich i leśnych)
- (−) brak dostępnej sieci oznacza brak transmisji do serwera
- (−) dłuższe opóźnienia i ograniczenia w odbiorze danych w dół mogą utrudniać szybką reakcję
- (−) gorzej radzi sobie, gdy nadajnik się przemieszcza między stacjami bazowymi, ale dla nieruchomego stosu to nie ma znaczenia
- (−) ponowne wyszukiwanie sieci i rejestracja przy słabym sygnale mogą zwiększać zużycie energii

### 4. LTE

- (−) LTE działa też na 800 MHz, jednak fale są tłumione
- (−) typowy modem LTE może mieć większy pobór energii niż dobrze skonfigurowany modem LPWAN
- (−) brak zasięgu LTE nadal oznacza brak transmisji, chyba że urządzenie ma alternatywny kanał łączności
- (−) przy sześciu krótkich wiadomościach dziennie możliwości transmisyjne LTE są w dużej mierze niewykorzystane

### 5. Satelita

- (−) fale tłumione są przez korony drzew i samo drewno. Moduł wymaga fizycznej widoczności nieba (Line-of-Sight), by namierzyć satelitę. Antena musi być wyprowadzona ze stosu (Iridium: widok w górę, Skylo: widok na południe)
- (−) problem to pobór prądu i konieczność wyprowadzenia anteny ze stosu (wielkość modułów może być również czasem większa)
- (−) moduły satelitarne pożerają prąd garściami w porównaniu do NB-IoT
- (−) mała bateria szybko padnie

---

## Zasięg sieci komórkowej w lesie

Polska ma dobre pokrycie powierzchniowe. Według UKE w kraju nie ma wielu miejsc bez zasięgu żadnej sieci mobilnej, ale sam zasięg nie gwarantuje jakości połączenia. Mapy operatorów to prognozy, a nie pomiary. W sporze z Aero2 UKE opierał się na mapach wyznaczonych metodą predykcji natężenia pola, co nie uwzględnia lasu ani stosu drewna.

- **NB-IoT ma ok. 20 dB zapasu więcej niż zwykłe LTE** i działa w paśmie 800 MHz. To mniej więcej odpowiada tłumieniu 100-200 m lasu lub warstwie mokrego drewna. Mygły leżą przy drogach, więc zwykle bliżej skraju lasu i nadajników niż środek drzewostanu.
- **Liście zmieniają niewiele w paśmie 800-900 MHz.** ITU podaje sezonowe wahania ok. 2 dB przy 900 MHz i ok. 8,5 dB przy 2200 MHz. To argument za niskimi pasmami (800 MHz) zamiast 1800/2100 MHz.

---

## Energia (wstępne rozeznanie)

Szczegóły po wyborze techniki. Najmniej zużywają LoRaWAN i NB-IoT/LTE-M w trybie PSM (ok. 1 mWh/dobę przy 6 wiadomościach). LTE Cat-1 bez PSM zużywa ok. 100 razy więcej, a satelita ok. 10-30 razy więcej na wiadomość.

---

## Ważny aspekt dotyczący NB-IoT/LTE-M przy PSM

1. Urządzenie budzi się i wysyła ramkę, np. HEARTBEAT.
2. Przez krótki czas po wysyłce (timer T3324, od 0 s do kilku minut) nasłuchuje. Serwer może wtedy odpowiedzieć, a odpowiedź dotrze od razu.
3. Potem urządzenie zasypia głęboko i jest nieosiągalne, ale pozostaje zarejestrowane w sieci.
4. Wiadomość od serwera wysłana w czasie snu może zostać przechowana przez sieć. U Telekomu w Niemczech to do 10 pakietów po 1600 B, ale limity zależą od operatora i nie są gwarantowane.
5. Alternatywa to eDRX: urządzenie co jakiś czas (od ok. 20 s do ok. 3 h) na chwilę nasłuchuje. Jest wtedy osiągalne szybciej, ale zużywa więcej energii.

Przy NB-IoT/LTE-M w trybie oszczędzania energii (PSM) oraz w LoRaWAN klasy A urządzenie może odebrać wiadomość od serwera tylko przez krótką chwilę po wysłaniu własnej ramki. Przez resztę czasu śpi i jest nieosiągalne. Komenda `FALSE_ALARM` lub `REAL_THEFT` kliknięta przez leśniczego trafi więc do węzła dopiero przy jego następnym kontakcie, czyli przy heartbeacie co 4-6 h. Ponieważ timeout blokady wynosi ok. 1 h, w praktyce urządzenie prawie zawsze odblokuje się samo, zanim komenda dotrze.

**Wniosek (Kacper):** przy tych rozwiązaniach serwer powinien trzymać kolejkę komend dla każdego urządzenia z czasem ważności, odsyłać je w odpowiedzi na dowolną ramkę od urządzenia i czekać na potwierdzenie (np. flaga lub licznik w kolejnej ramce), bo UDP nie gwarantuje dostarczenia. Komendy powinny być bezpieczne przy powtórzeniu (idempotentne), a odpowiedź leśniczego i tak warto zapisać w bazie jako etykietę dla Kiryla, nawet jeśli nie dotrze do węzła.

**Wniosek (Damian):** trzeba zdecydować, czy po alarmie urządzenie ma być szybciej osiągalne. Do wyboru jest częstsze budzenie się w czasie blokady (np. co 10-15 min krótka ramka z pytaniem o komendę) albo tryb eDRX na czas blokady. Obie opcje kosztują energię, więc powinniśmy policzyć ich wpływ na żywotność baterii. Bez tego zostaje sam timeout, a `SET_CONFIG` i `PING` zadziałają z opóźnieniem do najbliższego heartbeatu.

Źródła:

- <https://hub.iot.telekom.com/docs/device-to-cloud/general-info/nb-iot-network-information/>
- <https://hub.iot.telekom.com/docs/device-to-cloud/general-info/lte-m-network-information/>
- <https://www.thethingsnetwork.org/docs/lorawan/classes/>

---

## Koszty w Polsce za każdą z technik

### Sieć komórkowa

| Operator / technologia | Technologie | Cena (netto) | Uwagi |
|---|---|---|---|
| **Orange – Smart M2M** | LTE, LTE-M | Dane 0,10 zł za 1 MB, naliczane za każdy rozpoczęty 1 kB. Aktywacja 300 zł. | LTE-M działa tylko na specjalnych kartach telemetrycznych z APN „iot” i na modemach z listy Orange. PSM jest domyślnie włączony. NB-IoT nie występuje w cenniku. |
| **Orange – Taryfa Telemetryczna** | LTE, LTE-M | Pakiety danych od 5 zł/mies. za 5 MB. Ta sama stawka 0,10 zł/MB ponad pakiet. | Sprawdź w cenniku, czy dochodzi opłata za samą taryfę. |
| **Plus – Nowy M2M (od 10.11.2024)** | LTE (NB-IoT nie występuje w cenniku) | Abonament 46-50 zł/mies. z kwotą 1-5 zł do wykorzystania. Dane 0,10 zł/MB, naliczane za rozpoczęty 1 KB. | Wymaga REGON-u. To cena katalogowa, przy negocjacjach może być niżej. Ofertę NB-IoT Plus ma, ale bez publicznej ceny. |
| **T-Mobile** | NB-IoT (800 MHz, ponad 4300 stacji, cała Polska) | Brak publicznego cennika | To jedyny operator, który na stronie wprost opisuje swoją sieć NB-IoT. |
| **1NCE Lifetime Flat** | 2G/4G, LTE-M/NB-IoT tam, gdzie są dostępne | 12 € za 10 lat (500 MB + 250 SMS), karta SIM 1-2,50 € | Które technologie działają w Polsce, sprawdź w wierszu „Poland” na ich liście zasięgu. |

**Co to daje przy 6 wiadomościach dziennie?**
U Orange każda wiadomość liczy się jako co najmniej 1 kB, czyli ok. 180 kB miesięcznie. To ok. 0,02 zł miesięcznie za dane, więc liczą się głównie opłaty stałe: aktywacja, abonament, karta. LTE Cat-1 kosztuje tyle samo w abonamencie, bo operatorzy liczą dane, a nie technologię. Różnica wychodzi w cenie modułu i w zużyciu baterii.

> **Ważna uwaga praktyczna:** oferty M2M są dla firm (Plus wprost wymaga REGON-u). Dla naszego projektu studenckiego musimy się zapytać, czy kartę może zamówić uczelnia, albo zacznijmy od 1NCE lub dev-kitu z kartą w zestawie.

### Satelita

| Oferta | Cena | 6 wiadomości dziennie / rocznie |
|---|---|---|
| **Deutsche Telekom – dodatek satelitarny Skylo** | od 2,70 € za rok plus 0,90 € za KB danych satelitarnych | Do sprawdzenia, jak liczą KB. Gdyby każda wiadomość była zaokrąglana do 1 KB: ok. 1970 €/rok. Przy rozliczaniu faktycznych bajtów (ok. 60 B na wiadomość): ok. 120 €/rok. |
| **Blues + Skylo** | $0,00075 za bajt, minimum 50 B na pakiet | ok. $82/rok |
| **Iridium – RockBLOCK** | £13/mies. plus £0,04-0,11 za kredyt (1 kredyt = rozpoczęte 50 B) | ok. £240-400/rok |
| **Szacunek branżowy dla satelitarnego NB-IoT** | $0,50-1,50/mies. plus $0,01-0,05 za KB | ok. $7-25/rok, ale to dane od firmy konkurencyjnej wobec Skylo |

Wszystkie strony z kosztami znajdują się w [źródłach na końcu dokumentu](#cenniki). :)

---

## Obliczenia dotyczące ruchu danych

Założenia:

- dziennie: **6 wiadomości**
- wielkość payloadu każdej wiadomości: **20 B**
- dni w miesiącu: **30**
- liczba urządzeń: **1**

Na urządzenie: **3,6 kB** miesięcznie (3600 B payloadu).

Należy pamiętać, że w sieci komórkowej do każdej wiadomości dochodzą nagłówki IP/UDP/CoAP (ok. 40 B).

Z nagłówkami: (20 B + 40 B) × 6 × 30 = **ok. 10,8 kB miesięcznie**.

---

## Dodatkowy pomysł: śledzenie ciężarówki

*(jak starczy czasu i energii w urządzeniu)*

### Jak mogłoby to działać

1. Algorytm Kiryla rozpoznaje załadunek (dźwig HDS), potem dłuższą jazdę, czyli długie, ciągłe drgania typowe dla pojazdu.
2. Urządzenie wysyła `ALARM` i przechodzi w tryb śledzenia, zamiast się blokować.
3. Co np. 5-10 min wysyła ramkę z pozycją. Nowy typ ramki: `LOCATION`, ok. 8-10 B (szerokość i długość geograficzna plus dokładność).
4. Serwer rysuje trasę w aplikacji leśniczego i przekazuje ją policji.

### Skąd wziąć pozycję

- **GNSS (GPS):** dokładność rzędu metrów, ale potrzebuje widoku nieba. W środku kłody na naczepie może nie złapać sygnału. Jedna lokalizacja kosztuje wyraźnie więcej energii niż wysłanie ramki.
- **Lokalizacja z sieci komórkowej:** przybliżenie na podstawie stacji bazowych, z dokładnością od setek metrów do kilku kilometrów. Nie wymaga GPS ani widoku nieba i wystarcza, by ustalić kierunek jazdy albo tartak. 1NCE ma taką usługę: „Device Locator Plus”, 10 € za 10 000 lokalizacji.

**Dlaczego tu lepsze jest LTE-M:** obsługuje przełączanie między stacjami bazowymi w ruchu. NB-IoT jest projektowany głównie dla urządzeń stacjonarnych.

### Ryzyka i pytania do zespołu

- **Energia (Damian):** kilka godzin wysyłania co 5 min, ewentualnie z GPS, to dużo więcej niż normalny dzień pracy. Trzeba ustalić, ile godzin śledzenia bateria wytrzyma i kiedy urządzenie wraca do snu.
- **Zasięg:** metalowa naczepa i masa drewna mocno tłumią sygnał. Urządzenie może też wypaść przy załadunku.
- **Wykrywanie (Kiryl):** jak odróżnić jazdę ciężarówką od legalnej zrywki lub wywozu przez nadleśnictwo. Tu pomoże serwer, jeśli zna harmonogram legalnych wywozów.
- **Protokół (Kacper):** nowy typ ramki `LOCATION` i nowy stan „ŚLEDZENIE” na diagramie.
- **Procedura:** dane trafiają do policji. Leśniczy nie powinien sam ścigać złodziei.

---

## Linki i źródła

### Linki i ciekawe artykuły

- <https://biznes.t-mobile.pl/pl/produkty-i-uslugi/iot-smart-city-i-big-data/internet-rzeczy-iot>
- <https://www.com4.no/pl/blog/iot-komorkowe-i-satelitarne-kompletny-przewodnik-techniczny-dla-globalnych-wdrozen#what-is-satellite-ioT>
- <https://komorkomat.pl/mapa-zasiegu-t-mobile/>
- <https://laspolski.pl/3623-szybki-internet-dla-lesniczowek-i-do-pracy-w-lesie/>
- <https://support.digitalmatter.com/en_US/400987-general/330-packet-size-on-lora-networks-structure-of-network-pricing>
- <https://www.mdpi.com/1999-5903/13/5/115>
- <https://www.plus.pl/blog/technologie/pasma-lte-w-polsce-ktore-sa-najszybsze>
- <https://tmt.expert/tauron-przetestowal-techniki-radiowe-transmisji-danych-energetyce-lora-sigfox-nb-iot-lte-m-259/>
- <https://www.gsma.com/solutions-and-impact/technologies/internet-of-things/>
- <https://biznes.plus.pl/iot-m2m/be-smart/narrowband>
- <https://www.com4.no/pl/technologie/nb-iot-internet-rzeczy>
- <https://tele.agh.edu.pl/~kulakowski/satelity/geos.html>
- <https://stacjebazowe.pl/baza-wiedzy/pasma-czestotliwosci-w-polsce>

### Satelity

- <https://docs.groundcontrol.com/iot/rockblock/iridium>
- <https://www.eoportal.org/satellite-missions/iridium-next#mission-capabilities>
- <https://www.farnell.com/datasheets/3195933.pdf>
- <https://dev.blues.io/pdfs/datasheets/starnote-datasheet/starnote-for-skylo.pdf>

### Cenniki

- <https://orange-m2m.pl/smart.html?file=files%2Ffilemanager%2Fdokumenty%2Fsmart-2024%2FCennik+us%C5%82ug+w+ofercie+Smart+M2M+20241110.pdf>
- <https://orange-m2m.pl/tt10.html>
- <https://www.orange.pl/duze-firmy/m2m>
- <https://biznes.plus.pl/site/binaries/content/assets/portal-b2b/cenniki-taryfowe/cennik-uslug-komunikacji-elektronicznej-m2m.pdf>
- <https://a.storyblok.com/f/335000/x/23bb62a8c3/1nce_gmbh_price_list_01_2026.pdf>
- <https://a.storyblok.com/f/335000/x/72c42b6a8b/2025-10-1nce-coverage-1nce-for-all.pdf>
- <https://www.telekom.com/en/newsroom/latest-updates/media-information/2024/2/globally-connected-tariffs-for-satellite-connectivity-in-the-io>
- <https://hubble.com/community/comparisons/is-3gpp-ntn-worth-the-cost-breaking-down-module-premiums-lte-fees-and-satellite-surcharges/>
- <https://docs.px4.io/v1.13/en/advanced_features/satcom_roadblock>
- <https://docs.rockblock.rock7.com/docs/iridium-contract-costs>
- <https://thingsdata.pl/karty-sim-lte-m/>
- <https://www.com4.no/pl/blog/calkowity-koszt-posiadania-prawdziwy-benchmark-lacznosci-iot>
