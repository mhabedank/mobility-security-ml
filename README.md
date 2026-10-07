# mobility-security-ml

Machine-Learning-Modelle für **Mobility- und Automotive-Security**. Der Fokus liegt auf
**TinyML**: Die Modelle sollen auf kleinen Mikrocontrollern wie ESP32-S3, STM32 oder NXP S32K laufen.
Fertige Modelle werden auf **Hugging Face** unter einer eigenen Organisation veröffentlicht.

> Status: **Phase 0, Recherche.** Es gibt noch keinen Code. Die Ergebnisse liegen unter [`docs/research/`](docs/research/README.md).

## Worum es geht

Fahrzeuge und Mobilitätsgeräte haben viele Steuergeräte, Busse (CAN, CAN FD, LIN, Automotive Ethernet) und
Funkschnittstellen (Keyless, GNSS, BLE, V2X). Viele dieser Schnittstellen haben keine Authentifizierung.
Angriffe lassen sich oft nur über **Anomalien im Verhalten** erkennen, also über Timing,
Sequenzen, physikalische Plausibilität oder Funkmerkmale.

Die Erkennung soll direkt auf dem Gerät laufen: billig, mit wenig Energie, in Echtzeit und
ohne Cloud. So passt sie in die Architektur, die UNECE R155 und AUTOSAR IdsM vorsehen:
Security-Sensor → IdsM / Security Event Memory → Vehicle SOC.

## Dokumentation

| Dokument | Inhalt |
|---|---|
| [Recherche-Übersicht](docs/research/README.md) | Executive Summary und Einstieg |
| [01 – Bedrohungslandschaft](docs/research/01-bedrohungslandschaft.md) | Welche Security-Probleme lassen sich mit TinyML angehen? |
| [02 – Literatur](docs/research/02-literatur.md) | Wichtige Papers, MCU-Deployments, Fallstricke |
| [03 – Datensätze](docs/research/03-datensaetze.md) | Öffentliche Daten, Lizenzen, Eignung für Hugging Face |
| [04 – Hardware](docs/research/04-hardware.md) | Prozessoren und Boards, CAN-Anbindung, Laboraufbau |
| [05 – Toolchain & Publishing](docs/research/05-toolchain-und-publishing.md) | Training → Quantisierung → MCU → Hugging Face |
| [Roadmap](docs/roadmap.md) | Low-Hanging Fruits, Reihenfolge der Modelle, offene Entscheidungen |

## Lizenz

Der Code steht unter [Apache-2.0](LICENSE). Für trainierte Modelle können je nach Trainingsdaten andere
Lizenzen gelten. Siehe [Datensätze → Lizenzen](docs/research/03-datensaetze.md#lizenzen-was-dürfen-wir-veröffentlichen).
