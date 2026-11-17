# Powiadomienia push

Leśniczy dostaje na telefon powiadomienie o nowym alarmie, także gdy aplikacja jest zamknięta, a telefon zablokowany. Stuknięcie w powiadomienie otwiera ten alarm na liście.

Standardowy Web Push z kluczami VAPID, bez Firebase.

## Jak to wygląda

1. leśniczy otwiera **Menu** (☰). Na górze jest **Włącz powiadomienia o alarmach**
2. po stuknięciu przeglądarka pyta o zgodę. Pytanie pojawia się dopiero po kliknięciu, nigdy przy wejściu do aplikacji
3. po zgodzie w menu jest napis „Powiadomienia o alarmach włączone”
4. przy nowym alarmie telefon wibruje i pokazuje np. „Alarm: Skład przy drodze 5 – Możliwe podbieranie drewna, pewność 87%”
5. stuknięcie otwiera `/alarms/41`: listę alarmów z wyróżnionym alarmem ([alarmy.md, sekcja Adres](alarmy.md#adres)). Gdy aplikacja jest już otwarta, przechodzi do alarmu w tym samym oknie

Inne napisy w menu:

| Napis | Kiedy |
|---|---|
| Powiadomienia są zablokowane. Włącz je w ustawieniach strony… | użytkownik odmówił. Aplikacja nie może zapytać drugi raz: kłódka przy adresie → Uprawnienia → Powiadomienia |
| To urządzenie nie obsługuje powiadomień. | `http://` z adresem IP, `npm run dev` (bez service workera), stara przeglądarka albo iPhone (iOS nie jest wspierany, [pwa.md](pwa.md)) |

- powiadomienia ma tylko **leśniczy**. Nadleśniczy i admin nie mają tej opcji w menu (backend zwróciłby im `403`)
- ten sam alarm przysłany ponownie **podmienia** swoje powiadomienie, zamiast dokładać kolejne, ale telefon znowu wibruje
- powiadomienie otwiera tylko adresy aplikacji (zaczynające się od `/`). Inny adres w pushu otwiera mapę

## Wylogowanie

Subskrypcja należy do przeglądarki, a nie do konta. Żeby następna osoba na tym telefonie nie dostawała cudzych alarmów:

- **Wyloguj** kasuje subskrypcję w backendzie (z tokenem sprzed wylogowania) i w przeglądarce. Wylogowanie nie czeka na to, więc działa też bez internetu
- gdy sesja wygaśnie (`401` przy wejściu), przeglądarka też się wypisuje. Backend usuwa subskrypcję sam, gdy usługa push odpowie mu `410`
- gdy powiadomienia są już włączone, aplikacja przy wejściu po cichu wysyła subskrypcję jeszcze raz. Backend wie wtedy, kto jest teraz zalogowany na tym telefonie

## Dane

| Zapytanie | Kiedy |
|---|---|
| `GET /push/vapid-public-key` | przy włączaniu; klucz nie jest wpisany w aplikację |
| `POST /push/subscriptions` | po zgodzie i przy każdym wejściu, gdy włączone. Wysyłamy `subscription.toJSON()` i `device_label`, np. „Android – Chrome” |
| `DELETE /push/subscriptions?endpoint=…` | przy wylogowaniu |

Na mocku (`VITE_USE_MOCK=true`) subskrypcje są w pamięci i znikają po odświeżeniu strony. Przeglądarka pamięta swoją subskrypcję, więc przy wejściu aplikacja wyśle ją ponownie.