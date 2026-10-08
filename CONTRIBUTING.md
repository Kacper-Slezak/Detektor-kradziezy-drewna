# Jak pracować w repozytorium

Krótka instrukcja dla całego zespołu. Jeśli się zgubisz, wróć tutaj albo napisz do @Kacper-Slezak.

---

## Najważniejsza zasada

**Nigdy nie pracujemy bezpośrednio na `main`.**
Każda zmiana idzie przez własną gałąź (branch) i Pull Request (PR). GitHub i tak zablokuje push na `main`.

```
issue  →  gałąź  →  commity  →  push  →  Pull Request  →  review  →  merge
```

---

## 1. Jednorazowa konfiguracja (robisz raz)

```bash
git clone https://github.com/Kacper-Slezak/Detektor-kradziezy-drewna.git
cd <repo>
git config user.name  "Imię Nazwisko"
git config user.email "twoj-mail-z-githuba@example.com"
```

Nie lubisz terminala? Możesz używać **GitHub Desktop** albo zakładki Source Control w **VS Code**. Kroki są te same, tylko klikane.

---

## 2. Codzienna praca krok po kroku
> Project Menadżer musi tutaj wybrać sposób kontrolii polecam Issues + Kanban tablica

#### Przykład dla Issues + Kanban
```
Na tablicy projektu (zakładka **Projects**) wybierz issue ze swoim obszarem, przypisz się (Assignees) i przesuń je do **In progress**.
Nie ma issue? Najpierw je załóż (**Issues → New issue → Zadanie**).
```
### Krok 2: pobierz najnowszą wersję i utwórz gałąź - pracujemy zawsze na gałeziach nie zależnie od metody wydzielania task

```bash
git switch main
git pull
git switch -c feat/backend-ingest
```

Nazwy gałęzi:

| Rodzaj         | Wzór                      | Przykład                   |
|----------------|---------------------------|----------------------------|
| nowa funkcja   | `feat/<obszar>-<opis>`    | `feat/firmware-sleep-mode` |
| poprawka       | `fix/<obszar>-<opis>`     | `fix/frontend-login`       |
| dokumentacja   | `docs/<opis>`             | `docs/protocol-v2`         |

Obszary: `firmware`, `backend`, `frontend`, `detection`, `hardware`, `comms`, `docs`.

### Krok 3: pracuj i rób commity

```bash
git add .
git commit -m "feat(backend): endpoint do odbioru alarmów"
```

Format wiadomości: `typ(obszar): co zrobiłem`, np.:
- `feat(firmware): wybudzanie na przerwanie z akcelerometru`
- `fix(frontend): crash przy braku internetu`
- `docs(comms): pomiary zasięgu w lesie`

Rób małe commity, najlepiej kilka/kilkanaście zamiast jednego wielkiego na koniec tygodnia.

### Krok 4: wypchnij gałąź

```bash
git push -u origin feat/backend-ingest
```

Przy kolejnych pushach wystarczy samo `git push`.

### Krok 5: otwórz Pull Request

Na GitHubie pojawi się przycisk **Compare & pull request**.

- Tytuł jak commit: `feat(backend): endpoint do odbioru alarmów`
- Wypełnij szablon: co zmienione i jak przetestowane
- Wpisz `Closes #12` (numer issue), wtedy issue zamknie się samo po merge'u
- Dodaj etykietę obszaru, np. `area:backend`

Recenzenci przypiszą się **automatycznie** na podstawie pliku `.github/CODEOWNERS`. Nie musisz nikogo wybierać.

Praca jeszcze niegotowa, ale chcesz pokazać postęp? Otwórz PR jako **Draft**.

### Krok 6: review i merge

- Potrzebne jest **1 zatwierdzenie** od właściciela danego folderu.
- Ktoś poprosił o zmiany? Popraw lokalnie, zrób commit i push. PR zaktualizuje się sam.
- Po zatwierdzeniu kliknij **Squash and merge** i usuń gałąź (przycisk **Delete branch**).

Na koniec przesuń issue do **Done**, jeśli nie przesunęło się samo.

---

## 3. Kto co zatwierdza

| Folder        | Właściciel          | Zawsze mogą też zatwierdzić |
|---------------|---------------------|-----------------------------|
| `firmware/`   | @damian677          | @Kacper-Slezak, @nix746     |
| `backend/`    | @Kacper-Slezak      | @nix746                     |
| `frontend/`   | @AgataSlusarczyk    | @Kacper-Slezak, @nix746     |
| `detection/`  | @kirilol-ok         | @Kacper-Slezak, @nix746     |
| `hardware/`   | @carbon718          | @Kacper-Slezak, @nix746     |
| `comms/`      | @Martynka123-code   | @Kacper-Slezak, @nix746     |
| `docs/`       | cały zespół         |                             |
| `.github/`    | @Kacper-Slezak      |                             |

Nie da się zatwierdzić własnego PR-a.

---

## 4. Jak robić review cudzego PR-a

1. Otwórz PR → zakładka **Files changed**.
2. Komentarz do konkretnej linii: najedź na nią i kliknij **+**.
3. Na koniec **Review changes**:
   - **Approve**: wszystko OK,
   - **Request changes**: trzeba poprawić,
   - **Comment**: tylko uwagi.

Staraj się zrobić review w ciągu ludzkiego czasu, bo ktoś na Ciebie czeka.

---

## 5. Zmiany wspólne: format wiadomości

Plik `docs/` opisuje ważne dokumentacje, głównie dla nas są readme, ale są wspóle też   

---

## 6. Czego NIE robić

- Pushowanie na `main`.
- `git push --force` na cudzej gałęzi.
- Wrzucanie haseł, kluczy, tokenów i plików `.env`. Sekrety trzymamy w `.env` (jest w `.gitignore`) i w GitHub Secrets.
- Wrzucanie dużych nagrań i zbiorów danych. Idą na wspólny dysk, a do repo trafia tylko link i kilka próbek.
- Jeden ogromny PR na koniec sprintu. Lepiej kilka małych.

---

## 7. Najczęstsze problemy

**„Pracowałem na `main` i zrobiłem commit, a push jest odrzucony”**

```bash
git switch -c feat/moja-zmiana   # przenosi Twoje commity na nową gałąź
git push -u origin feat/moja-zmiana
git switch main
git reset --hard origin/main     # czyści lokalny main
```

**„PR ma konflikt z `main`”**

```bash
git switch main
git pull
git switch feat/moja-gałąź
git merge main
# popraw pliki oznaczone konfliktem (VS Code podświetla je i ma przyciski)
git add .
git commit
git push
```

Nie wiesz, którą wersję zostawić? Zapytaj autora drugiej zmiany.

**„Wrzuciłem przez przypadek hasło lub klucz”**

Natychmiast napisz do @Kacper-Slezak. Klucz trzeba **unieważnić i wygenerować nowy**, bo samo usunięcie pliku nie wystarczy, skoro klucz został w historii.

---

## 8. Ściągawka

```bash
git status                       # co się zmieniło
git switch main && git pull      # najnowszy main
git switch -c feat/obszar-opis   # nowa gałąź
git add . && git commit -m "..." # zapisz zmiany
git push                         # wyślij na GitHuba
git log --oneline -10            # ostatnie commity
git diff                         # co dokładnie zmieniłem
```
