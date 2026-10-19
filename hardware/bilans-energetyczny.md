# Bilans energetyczny

Poniższy dokument zawiera wymagania i obliczenia dotyczące zużycia energii.

## Wydajność prądowa
- Maksymalny prąd wyjściowy dla płytki `LoPy` na wyjściu `3.3V` wynosi `400mA`

### Zapotrzebowanie prądowe komponentów:
- **Idle (no radios)**: 37 mA
- **LoRa Transmit**: 92,6 mA (to już ESP32 + LoRa)
- **Czujnik wibracji**: 1 mA
- **Mikrofon**: 0,5 mA

Maksymalny pobór nie powinien przekroczyć 100 mA.

> [!WARNING]
> Pojawił się jednak mega duży problem. Urządzenie LoPy nie obsługuje chyba deep sleep mode. \
> W związku z tym na tym etapie oszacowanie czasu pracy na baterii dla tego zestawu jest bez sensu.


  ```
  Due to a couple issues with the LoPy design the module draws more current than it should while in deep sleep. The DC–DC switching regulator always stays in high performance mode which is used to provide the lowest possible output ripple when the modules is in use. In this mode, it draws a quiescent current of 10mA. When the regulator is put into ECO mode, the quiescent current goes down to 10uA. Unfortunately, the pin used to control this mode is out of the RTC domain, and therefore not usable during deep sleep. This causes the regulator to always stay in PWM mode, keeping its quiescent current at 10mA. Alongside this the flash chip doesn’t enter power down mode because the CS pin is floating during deep sleep. This causes the flash chip to consume around 2mA of current. Only the WiPY 2.0, LoPy 1.0 and SiPy 1.0 are affected by these issues. To work around this issue a “deep sleep shield” is available that attaches to the module and allows power to be cut off from the device. The device can then be re–enabled either on a timer or via pin interrupt. With the deep sleep shield the current consumption during deep sleep is between 7uA and 10uA depending on the wake sources configured.
```
Źródło: [Dokumentacja techniczna pkt 10.2](https://docs.pycom.io/gitbook/assets/specsheets/Pycom_002_Specsheets_LoPy_v2.pdf)