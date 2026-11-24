# Szyfrowanie ramek (AES-128)

Ramki z urządzeń mogą lecieć zaszyfrowane, żeby ich treść nie była czytelna po drodze (Wi-Fi, tunel, internet). Backend odszyfrowuje je w `POST /api/v1/ingest` przed dekodowaniem.

## Jak to działa

**Urządzenie:**

1. buduje jawną ramkę protokołu (wersja 3: 8–12 B, starsze 6–10 B),
2. dopełnia ją zerami do 16 B (jeden blok AES),
3. szyfruje AES-128-ECB kluczem `FRAME_AES_KEY`,
4. wysyła 16 B szyfru jako `payload_hex` (32 znaki hex).

```
31002a000301035a003cc858  ->  31002a000301035a003cc85800000000  ->  6aacf85f6340462158668848121cbe9d
jawna ramka (ALARM v3)        dopełnienie do 16 B                    szyfr (przykładowy klucz 0011…eeff)
```

Wektory testowe dla przykładowego klucza `00112233445566778899aabbccddeeff` (do sprawdzenia płytki):

| Jawna ramka | Szyfr |
|---|---|
| `33002A0001010158` (BOOT v3, `boot_id` 42, licznik 1) | `ACC4DBA45DCC36C95EF0F991DE0FEEA3` |
| `32002A0002580000` (HEARTBEAT v3, licznik 2) | `392E24511FD04F1F1178EADDA6BCB531` |
| `31002A000301035A003CC858` (ALARM v3, licznik 3) | `6AACF85F6340462158668848121CBE9D` |
| `130001010158` (BOOT v1) | `4E8B49D27D5B10A107CFD1092F329126` |

**Backend** (`decrypt_payload_hex` w `app/protocol/decoder.py`):

1. odszyfrowuje 16 B tym samym kluczem,
2. z pierwszego bajtu (wersja i typ) bierze długość jawnej ramki: `frame_length()`, np. wersja 3: BOOT i HEARTBEAT 8 B, ALARM 12 B; starsze: BOOT v1 6 B, BOOT v2 8 B, ALARM 10 B,
3. obcina dopełnienie i przekazuje jawną ramkę do dekodera; dalej wszystko jak dla ramki jawnej.

Dopełnienia nie obcinamy „po zerach”: HEARTBEAT sam kończy się bajtami `00 00`. W bazie (`messages.payload_hex`) zapisujemy ramkę jawną.

Tryb ECB jest tu wystarczający, bo wiadomość ma dokładnie jeden blok, a para (`boot_id`, licznik) w ramce zmienia się przy każdej wiadomości, więc identyczne zdarzenia dają różne szyfry.

## Konfiguracja

| `FRAME_AES_KEY` | Zachowanie `/ingest` |
|---|---|
| ustawiony (32 znaki hex) | tylko ramki zaszyfrowane (16 B); **jawna ramka → `422`**; zły klucz → `422` |
| pusty | bez szyfrowania: tylko ramki jawne |

Jawne ramki są odrzucane przy ustawionym kluczu, bo inaczej fałszywą ramkę (np. ALARM) dałoby się wysłać bez znajomości klucza.

Generowanie klucza: `python -c "import secrets; print(secrets.token_hex(16))"`. Ten sam klucz w `backend/.env` i na płytce, nigdy w repo. Zły format klucza (nie hex albo nie 16 B) zatrzymuje backend przy starcie.

Symulator i przykłady `curl` z [testowanie.md](../testowanie.md) wysyłają ramki jawne, więc działają tylko przy pustym `FRAME_AES_KEY`.

## Czego to nie robi

- **Nie uwierzytelnia ramek**: brak podpisu (MIC). Powtórki nagranych pakietów odrzuca para (`boot_id`, licznik) w ramce wersji 3 ([boot-id.md](boot-id.md)), ale kto zna klucze, może zbudować nową ramkę.
- **Nie chroni `X-Ingest-Key`**: przy zwykłym HTTP nagłówek idzie jawnie.
- Uwierzytelnienie ramek (tag, AES-CCM, klucze per czujnik) to osobny krok.
