# Wydania drewna (wyciszanie czujnika)

Gdy leśniczy wydaje drewno przewoźnikowi, wycisza czujnik przy tym składzie. W tym czasie czujnik nadal wysyła ramki, ale backend nie robi z nich alarmów, więc legalny wywóz nie kończy się alarmem.

## Wyciszenie z mapy

1. stuknięcie pinezki, w dymku przycisk **Wycisz na czas wywozu** (tylko leśniczy)
2. wysuwa się panel **Wyciszenie na czas wywozu**:
   - **Czas wyciszenia**: **1 h / 2 h / 4 h**, domyślnie 4 h. Pod spodem „Czujnik zacznie znów czuwać o 18:05”, godzina przesuwa się, gdy formularz jest dłużej otwarty
   - **Przewoźnik**, **Liczba kłód**, **Komentarz**: opcjonalne, do ewidencji i sporów z przewoźnikiem. Puste pola nie są wysyłane
   - **Wycisz**
3. nad mapą pojawia się „Wyciszono: Skład przy paśniku do 20.11.2026, 18:05”, a pinezka od razu robi się niebieska
4. po upływie czasu czujnik sam wraca do czuwania, nic nie trzeba klikać

## Zakończenie wcześniej

Przewoźnik odjechał przed czasem, więc leśniczy kończy wyciszenie, żeby czujnik znów pilnował składu:

1. niebieska pinezka, w dymku **Zakończ wyciszenie**
2. panel **Zakończyć wyciszenie?** z tekstem „Czujnik „…” znów będzie zgłaszał alarmy.” i przyciskami **Anuluj** / **Zakończ**. Drugie stuknięcie jest po to, żeby przypadkiem nie obudzić czujnika w trakcie załadunku
3. nad mapą „Skład przy szlabanie znów czuwa”, pinezka wraca do zielonej

Gdy wyciszenie właśnie minęło albo zakończył je ktoś inny, aplikacja też pokazuje sukces, bo czujnik i tak już czuwa.

## Który przycisk w dymku

| Czujnik | Przycisk |
|---|---|
| czuwa (zielony, pomarańczowy) | Wycisz na czas wywozu |
| wyciszony (niebieski) | Zakończ wyciszenie |
| alarm, który przyszedł przed wyciszeniem (czerwony) | Zakończ wyciszenie. Pinezka zostaje czerwona, dopóki leśniczy nie odpowie na alarm |
| wyłączony (szary) | brak, bo i tak nie wysyła alarmów |

Nadleśniczy nie ma tych przycisków (backend zwróciłby mu `403`). Admin nie korzysta z mapy.

## Panel wydań

Przycisk **🚚 Wydania** w górnym pasku, obok Mapy i Alarmów (adres `/releases`). Niebieska liczba przy nim to trwające wyciszenia. Leśniczy widzi wydania swojego leśnictwa, nadleśniczy wszystkich leśnictw.

**Trwające**:

- karta dla każdego wyciszonego czujnika: do kiedy i ile jeszcze, przewoźnik i kłody, komentarz, kto i od kiedy
- leśniczy ma na karcie **Zakończ wyciszenie**, z tym samym pytaniem co w dymku na mapie. Po zakończeniu karta znika, liczba przy przycisku maleje, a pinezka na mapie wraca do zielonej
- lista odświeża się co 20 s, a wyciszenie, które minęło, znika samo
- pusto: „Żaden czujnik nie jest teraz wyciszony.”

**Historia**, czyli zakończone wydania, od najnowszych, do raportów i sporów z przewoźnikiem:

- filtr **Czujnik** (lista czujników, które widać na mapie) i **Okres**: 7 dni / **30 dni** (domyślnie) / Rok / Wszystko. „30 dni” to wydania, które choć częściowo trwały w ostatnich 30 dniach
- po 50 naraz; **Pokaż starsze** dociąga kolejne z tymi samymi filtrami
- historia nie odświeża się sama, tylko przy zmianie filtra albo zakładki
- karty bez przycisków, z czasem od–do („14.10.2026, 08:00 – 11:20”)

Nadleśniczy widzi obie zakładki, ale bez przycisku kończenia, bo backend pozwala wyciszać i kończyć tylko leśniczemu i adminowi.

## Dalej

- push `release_ended`, gdy wyciszenie się skończy (wymaga backendu push)
