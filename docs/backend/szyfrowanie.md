# Szyfrowanie ramek (AES-128)

Ramki z urządzeń mogą lecieć zaszyfrowane, żeby ich treść nie była czytelna po drodze (Wi-Fi, tunel, internet). Backend odszyfrowuje je w `POST /api/v1/ingest` przed dekodowaniem.

## Jak to działa

**Urządzenie:**

1. buduje jawną ramkę protokołu (6–10 B),
2. dopełnia ją zerami do 16 B (jeden blok AES),
3. szyfruje AES-128-ECB kluczem `FRAME_AES_KEY`,
4. wysyła 16 B szyfru jako `payload_hex` (32 znaki hex).

```
130001010158  ->  13000101015800000000000000000000  ->  4e8b49d27d5b10a107cfd1092f329126
jawna ramka       dopełnienie do 16 B                    szyfr (przykładowy klucz 0011…eeff)
```

**Backend** (`decrypt_payload_hex` w `app/protocol/decoder.py`):

1. odszyfrowuje 16 B tym samym kluczem,
2. z pierwszego bajtu (wersja i typ) bierze długość jawnej ramki: `frame_length()`, np. BOOT v1 6 B, BOOT v2 8 B (z `boot_id`), ALARM 10 B,
3. obcina dopełnienie i przekazuje jawną ramkę do dekodera; dalej wszystko jak dla ramki jawnej.

Dopełnienia nie obcinamy „po zerach”: HEARTBEAT sam kończy się bajtami `00 00`. W bazie (`messages.payload_hex`) zapisujemy ramkę jawną.

Tryb ECB jest tu wystarczający, bo wiadomość ma dokładnie jeden blok, a licznik w ramce zmienia się przy każdej wiadomości, więc identyczne zdarzenia dają różne szyfry.

## Konfiguracja

| `FRAME_AES_KEY` | Zachowanie `/ingest` |
|---|---|
| ustawiony (32 znaki hex) | tylko ramki zaszyfrowane (16 B); **jawna ramka → `422`**; zły klucz → `422` |
| pusty | bez szyfrowania: tylko ramki jawne |

Jawne ramki są odrzucane przy ustawionym kluczu, bo inaczej fałszywą ramkę (np. ALARM) dałoby się wysłać bez znajomości klucza.

Generowanie klucza: `python -c "import secrets; print(secrets.token_hex(16))"`. Ten sam klucz w `backend/.env` i na płytce, nigdy w repo. Zły format klucza (nie hex albo nie 16 B) zatrzymuje backend przy starcie.

Symulator i przykłady `curl` z [testowanie.md](../testowanie.md) wysyłają ramki jawne, więc działają tylko przy pustym `FRAME_AES_KEY`.

## Czego to nie robi

- **Nie uwierzytelnia ramek**: brak podpisu (MIC), więc nagrany zaszyfrowany pakiet można wysłać ponownie. Licznik odrzuca duplikaty, a powtórkę BOOT zamyka `boot_id` ([boot-id.md](boot-id.md)).
- **Nie chroni `X-Ingest-Key`**: przy zwykłym HTTP nagłówek idzie jawnie.
- Uwierzytelnienie ramek (tag, AES-CCM, klucze per czujnik) to osobny krok.
