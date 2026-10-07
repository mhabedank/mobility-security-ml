# Trainingsdaten: Auswahl, Lizenzen, Hosting

Ziel: realistische, offen lizenzierte Daten für **mehrere Use Cases**, die wir auch
kommerziell nutzen und – wo erlaubt – auf dem Hugging Face Hub spiegeln dürfen.
Die Daten liegen **nie im Repository**: `hilbench data download <id>` lädt sie vom
Originalanbieter nach `$HILBENCH_DATA` (Standard `~/.cache/hilbench/datasets`) und
protokolliert Herkunft, Lizenz, Abrufzeit und SHA-256 in `SOURCE.json`.

> Keine Rechtsberatung. Die Bewertung beruht auf den Lizenzangaben der Anbieter
> (Stand Oktober 2026, für Zenodo maschinell geprüft) und sollte vor einer
> Veröffentlichung von eurer Rechtsabteilung bestätigt werden.

## Ausgewählt

| ID | Use Case | Lizenz | kommerziell | HF-Mirror erlaubt | Größe | Status |
|---|---|---|---|---|---|---|
| `speech-commands` | Keyword Spotting / Sprachsteuerung im Fahrzeug | CC BY 4.0 | ja | ja (existiert bereits: `google/speech_commands`) | 2,3 GB | **trainiert** (`kws_dscnn`) |
| `uci-har` | IMU-Bewegungserkennung (Beschleunigung + Gyro, 6 Aktivitäten) | CC BY 4.0 | ja | ja | 60 MB | **trainiert** (`har_cnn1d`) |
| `road` | CAN-Bus-Intrusion-Detection (echtes Fahrzeug, Fuzzing, Fabrication, Masquerade) | CC BY 4.0 | ja | ja | 560 MB | **trainiert** (`can_ids_road`) |
| `can-mirgu` | CAN-IDS auf modernem Fahrzeug während der Fahrt | CC BY 4.0 | ja | ja | 500 MB | **beim Anbieter defekt**: Das UCI-Zip enthält statt Header und Datenanfang ~180 MB Nullbytes, nicht rekonstruierbar. Der Downloader verweigert es mit Begründung, CAN-IDS deckt `road` ab |
| `mimii` | Anomalie-Erkennung an Maschinengeräuschen (Lüfter, Pumpen, Ventile; Predictive Maintenance) | CC BY-SA 4.0 | ja | ja, **Share-Alike** | 10 GB pro Maschine/SNR; wir lesen per HTTP-Range nur ~1150 Clips (~2 GB) | **trainiert** (`mimii_fan_ae`, Gewichte unter CC BY-SA 4.0) |

### Bezug zur Mobilität

Nicht jeder Datensatz stammt aus einem Fahrzeug. Für die beiden, bei denen das nicht
offensichtlich ist, steht hier, warum sie im Mobility-Zoo sind und wo ihre Grenzen liegen.

**`mimii`: Akustische Zustandsüberwachung von Nebenaggregaten.** Lüfter, Pumpen, Ventile
und Schienenführungen sind genau die Komponenten, die in Fahrzeugen und Mobilitätsinfrastruktur
verschleißen. Beispiele: Batterie- und Leistungselektronik-Kühlung im E-Fahrzeug (Lüfter,
Kühlmittelpumpen), Klimagebläse, Kühlung von DC-Schnellladesäulen, Pumpen und Ventile in
Schienenfahrzeugen, Schiebetüren in Bus und Bahn. Ein Mikrofon plus Mikrocontroller erkennt
abweichende Geräusche, bevor das Bauteil ausfällt. Das ist Predictive Maintenance für Flotten
und Ladeinfrastruktur ohne Cloud-Anbindung. Das Verfahren braucht nur Aufnahmen im Normalzustand,
was im Feld der Regelfall ist.
*Grenze:* Die Aufnahmen stammen aus einer Fabrikhalle, nicht aus einem Fahrzeug. Das Modell
belegt, dass Pipeline und Hardware tragen. Für den Einsatz an einem konkreten Aggregat trainieren
wir mit eigenen Normalaufnahmen nach.

**`uci-har`: Bewegungserkennung aus IMU-Daten.** Beschleunigungs- und Drehratensensoren
stecken in jedem Smartphone, Wearable, E-Scooter und Steuergerät. Das Modell zeigt, wie
Fenster aus 6-Achsen-IMU-Daten auf dem Mikrocontroller klassifiziert werden: Gehen,
Treppe, Sitzen, Stehen, Liegen. Mobilitätsbezug hat das bei Fußgängern und Mikromobilität
(z. B. Sturzerkennung), bei multimodaler Wegeerkennung und als
Vorstufe für Fahrmanöver- oder Fahrstilerkennung mit derselben Architektur.
*Grenze:* Es gibt keine Fahrzeugklassen (Auto, Bus, Rad), und der Sensor saß am Gürtel.
Für Verkehrsmittel- oder Manövererkennung braucht es andere Daten bei gleicher Pipeline.

Lizenzprüfung: `hilbench data verify` vergleicht die Lizenz, die der Anbieter **heute**
deklariert (Zenodo-API), mit der Registry. Ein Lizenzwechsel lässt den CI-Job
`datasets / verify-licenses` fehlschlagen.

## Abgelehnt

| Datensatz | Grund |
|---|---|
| SynCAN (ETAS) | nur nicht-kommerzielle Nutzung |
| HCRL Car-Hacking / OTIDS | Download nur nach Registrierung, keine offene Weitergabe-Lizenz |
| DCASE 2021+ Task 2 / ToyADMOS2 | CC BY-NC-SA 4.0 (nicht kommerziell) |
| DCASE 2020 Task 2 Dev (MIMII+ToyADMOS-Teilmengen) | Zenodo deklariert CC BY-NC-SA 4.0. Von `hilbench data verify` erkannt, obwohl die Quelldaten CC BY-SA sind |
| GNSS Interference & Spoofing (Mendeley) | CC BY-NC (nicht kommerziell) |
| driverBehaviorDataset (GitHub jair-jr) | keine Lizenz = alle Rechte vorbehalten |

GNSS-Spoofing: Offen lizenzierte Daten (FGI-SpoofRepo, Tuni2025, beide CC BY 4.0)
sind rohe I/Q-Aufnahmen. Für eine MCU-Inferenz auf Navigationslösungsebene müsste
man sie erst durch einen Software-Receiver schicken; das ist ein eigener
Arbeitsschritt und deshalb noch nicht im Zoo.

## Dürfen wir fremde Daten auf Hugging Face hosten?

| Lizenz | Spiegeln erlaubt? | Bedingungen |
|---|---|---|
| CC BY 4.0 | **ja** | Namensnennung (Autoren, Titel, Lizenz-Link), Hinweis auf Änderungen; keine zusätzlichen Einschränkungen (z. B. kein Gating, das die Lizenz einschränkt) |
| CC BY-SA 4.0 | **ja** | wie CC BY, zusätzlich muss der Mirror **und jede abgeleitete Datenfassung** (z. B. vorberechnete Features) unter CC BY-SA 4.0 stehen |
| CC BY-NC(-SA) | für kommerzielle Projekte **nein** | – |
| ohne Lizenz / "auf Anfrage" | **nein** | – |

`hilbench hub mirror-dataset <id> --org <org>` spiegelt nur Datensätze, die die
Registry als `hf_rehost: yes…` markiert. Die Dateien bleiben unverändert, und die Dataset Card
enthält Attribution, Zitat und Lizenz.

**Modelle:** Gewichte, die auf CC-BY-Daten trainiert wurden, veröffentlichen wir unter
Apache-2.0 mit Attribution der Trainingsdaten in der Model Card. Bei CC-BY-SA-Daten ist
umstritten, ob Gewichte eine Bearbeitung sind; vorsichtshalber setzt `hilbench hub` dann
`cc-by-sa-4.0` für das Modell.

## Ablauf

```bash
hilbench data list                    # Registry + abgelehnte Datensätze
hilbench data verify                  # Lizenzen beim Anbieter prüfen
hilbench data download uci-har        # nach $HILBENCH_DATA
hilbench train har --download         # trainieren, int8 exportieren, bit-exakt prüfen
hilbench run -b sim                   # HIL-Suite inkl. Genauigkeit auf dem Gerät
```

**Große Archive:** Bei `mimii` lädt der Downloader nicht das 10-GB-Zip, sondern liest
per HTTP-Range nur das zentrale Verzeichnis und danach jede ausgewählte Datei mit einer
einzigen Range-Anfrage (CRC-geprüft, parallel). Die Auswahl (Glob + Anzahl, fester Seed)
steht in der Registry (`zip_members`) und wird in `SOURCE.json` protokolliert.

In CI: `models/train-request.json` ändern und pushen. Der Workflow `train` lädt die Daten,
trainiert, testet und committet ausschließlich Modellparameter und Berichte zurück.
