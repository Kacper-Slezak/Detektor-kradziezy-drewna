# Detekcja

## Analiza danych uciętych

### 1. Cel

Celem jest rozpoznawanie zdarzeń mogących wskazywać na **nieuprawnione przemieszczanie lub załadunek składowanego drewna** na podstawie danych z trzech czujników:

- **Akcelerometr** – rejestruje przyspieszenia, wstrząsy i zmiany położenia.
- **Mikrofon** – rejestruje dźwięki otoczenia, m.in. pracę pojazdów, uderzenia i odgłosy przemieszczanego drewna.

Urządzenie powinno oszczędzać energię, dlatego część danych może być rejestrowana **dopiero po wykryciu aktywności**. Zadaniem analizy nie jest automatyczne stwierdzenie kradzieży, lecz wykrycie podejrzanego zdarzenia i przekazanie go do dalszej weryfikacji, np. na podstawie harmonogramu dozwolonych prac.

### 2. Co oznaczają „dane ucięte”?

W kontekście sygnałów z czujników chodzi przede wszystkim o **niepełne fragmenty szeregów czasowych**:

- **Ucięty początek** – urządzenie rozpoczęło rejestrację po rozpoczęciu zdarzenia.
- **Ucięty koniec** – rejestracja zakończyła się przed zakończeniem zdarzenia.
- **Luki czasowe** – między zapisanymi fragmentami występują okresy bez pomiarów.
- **Różne długości fragmentów** – poszczególne nagrania lub serie pomiarów nie obejmują tego samego przedziału czasu.

**Uwaga terminologiczna:** w statystyce *truncation* oznacza często sytuację, w której część obserwacji w ogóle nie trafia do próby, a *censoring* – sytuację, gdy znamy tylko ograniczenie czasu zdarzenia. Nie należy utożsamiać tych pojęć ze zwykłym przycięciem nagrania. W projekcie mogą wystąpić zarówno ucięte fragmenty sygnałów, jak i **selekcja danych zależna od progu wybudzenia**: ciche zdarzenia będą rzadziej rejestrowane.

### 3. Metody analizy

#### 3.1. Threshold Detection z histerezą

Przekroczenie ustalonego progu przyspieszenia lub poziomu dźwięku może uruchamiać dokładniejszą rejestrację i analizę. Histereza (różne progi włączenia i wyłączenia) ogranicza częste przełączanie przy sygnale oscylującym w pobliżu progu. Metoda sprzyja oszczędzaniu energii, ale **nie rozpoznaje rodzaju zdarzenia** i może pomijać zdarzenia zbyt ciche lub słabe.

#### 3.2. Feature Extraction

Z krótkich fragmentów można wyliczać cechy, np. RMS, maksimum, wariancję i energię drgań, a dla dźwięku także cechy widmowe. Pozwala to porównywać fragmenty o różnej długości bez analizowania każdej próbki osobno. Trzeba jednak uwzględnić czas trwania fragmentu, ponieważ niektóre miary (np. suma energii) zależą od liczby próbek.

#### 3.3. Change Point Detection

Metoda wyszukuje momenty istotnej zmiany właściwości sygnału, np. przejście od spokojnego tła do serii wstrząsów. Może pomóc wskazać początek i koniec aktywności wewnątrz dostępnego fragmentu, nawet gdy nie znamy początku całego zdarzenia. Nie określa jednak samodzielnie, czy przyczyną była kradzież, ruch pojazdu czy naturalne zakłócenie.

#### 3.4. Analiza widmowa (STFT / spektrogram)

Krótkoczasowa transformata Fouriera opisuje, jak rozkład częstotliwości dźwięku zmienia się w czasie. Może pomóc odróżnić długotrwały odgłos silnika od krótkich uderzeń lub szumu otoczenia. Nawet niepełny fragment nagrania może zawierać użyteczne cechy, choć utrata początku lub końca zdarzenia ogranicza kontekst.

#### 3.5. Anomaly Detection

Model anomalii może uczyć się typowych wzorców spokoju, wiatru i zwykłego ruchu w otoczeniu, a następnie wskazywać nietypowe fragmenty dźwięku lub drgań. Jest przydatny, gdy brakuje wielu przykładów rzeczywistych prób kradzieży. Wynik powinien oznaczać **nietypową aktywność**, a nie pewne rozpoznanie kradzieży; ponadto dane zebrane wyłącznie po wybudzeniu mogą słabo reprezentować normalne tło.

#### 3.6. Analiza w krótkich oknach czasowych (Sliding Window)

Po wybudzeniu urządzenia sygnał można dzielić na zachodzące na siebie, krótkie okna i oceniać aktywność w każdym z nich. Pozwala to wykrywać powtarzalne uderzenia lub ciągłą pracę maszyny zamiast reagować wyłącznie na pojedynczy impuls. Ta metoda **nie wymaga stałego działania głównego procesora**: okna mogą być analizowane tylko podczas aktywnej rejestracji.

#### 3.7. Sensor Fusion i analiza sekwencji zdarzeń

Wyniki z mikrofonu i akcelerometru można łączyć na podstawie znaczników czasu. Na przykład seria uderzeń i odgłosy pracy pojazdu w krótkim odstępie mogą być bardziej znaczące niż każdy sygnał osobno. Ponieważ początek zdarzenia może być ucięty, algorytm nie powinien wymagać wystąpienia **wszystkich** elementów sekwencji w ustalonej kolejności.

#### 3.8. Analiza brakujących fragmentów i jakości danych

Dla każdego zapisu warto przechowywać czas rozpoczęcia, czas zakończenia, źródło wybudzenia oraz informację o przerwach w pomiarach. Algorytm może wtedy obniżać pewność oceny, gdy dysponuje jedynie końcówką zdarzenia albo krótką serią próbek. **Brak zapisu nie jest dowodem braku aktywności**, dlatego długich luk nie należy automatycznie wypełniać wartościami zerowymi ani sztucznie odtwarzać niezaobserwowanych zdarzeń.

### 4. Metody o niższym priorytecie

- **Padding i masking** – przydatne głównie wtedy, gdy wybrany model ML wymaga wspólnego rozmiaru wejścia. Nie odtwarzają utraconych pomiarów, więc nie są konieczne do pierwszych analiz.
- **Interpolacja** – może pomóc przy pojedynczych brakujących próbkach, lecz jest ryzykowna w przypadku wstrząsów i krótkich, gwałtownych zdarzeń.
- **Dynamic Time Warping (DTW)** – może służyć do porównywania podobnych przebiegów o różnym tempie, ale na początkowym etapie nie musi dawać wystarczającej korzyści w stosunku do kosztu obliczeń.
