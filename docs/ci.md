# CI mit echten Boards

## Was wo läuft

| Workflow | Runner | Inhalt |
|---|---|---|
| `ci.yml` | GitHub-hosted | Unit-Tests, HIL-Suite gegen simulierte Boards, Firmware-Build für alle Targets mit Größenübersicht |
| `hil.yml` | **self-hosted, Label `hil`** | `hilbench run --parallel --slow` auf allen angeschlossenen Boards, nächtlich und manuell |

## Self-hosted Runner auf dem HIL-Host einrichten

1. Host vorbereiten: `sudo ./hil/setup-host.sh` (dialout, udev, uhubctl) und
   `hil/boards.yaml` mit den echten Boards pflegen (`hilbench discover`, dann `hilbench list`).
2. GitHub → *Settings → Actions → Runners → New self-hosted runner*. Den Anweisungen folgen und
   beim `config.sh` das zusätzliche Label `hil` vergeben. Den Runner als Dienst installieren
   (`sudo ./svc.sh install && sudo ./svc.sh start`) und den Dienstbenutzer in die Gruppe
   `dialout` aufnehmen.
3. Optional dieselben Lock-Verzeichnisse für Menschen und CI nutzen, damit sich ein
   interaktiver Test und ein CI-Lauf nie dasselbe Board teilen:
   `lab: {lock_dir: /var/lock/hilbench}` in `hil/boards.yaml`.
4. *Actions → hil → Run workflow* startet einen Lauf, optional mit Board-Liste und Smoke-Modus.

## Baseline / Performance-Regressionen

Nach einem guten Lauf `results/hil/summary.json` als `hil/baseline.json` einchecken. Von da an
schlägt `test_benchmark` fehl, sobald ein Modell auf einem Board mehr als 25 % langsamer wird
(`--tolerance`). Feste Obergrenzen pro Target und Modell setzt man in `hil/targets.yaml`:

```yaml
esp8266:
  budgets: {can_ids_road: 5000, har_cnn1d: 1000000}   # Mikrosekunden
```

## Artefakte

Jeder Lauf lädt `results/…` hoch: `summary.md`, `summary.json`, `junit.xml`, `metrics/*.jsonl`
und pro Board das komplette serielle Log (inklusive aller Host-Befehle). Die Zusammenfassung
erscheint außerdem direkt auf der Workflow-Seite.
