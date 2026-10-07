# Bench-Protokoll (Version 1)

Zeilenbasiert über die serielle Schnittstelle (115200 Baud, 8N1).

* Host → Gerät: `#<id> <BEFEHL> [arg …]\n`
* Gerät → Host: `@{json}\n`. Alle anderen Zeilen (Bootloader-Ausgaben, Crash-Dumps) sind Log
  und werden von der Bench in `logs/<board>.log` gespeichert.
* Jede Antwort enthält `"id"` (die Request-ID) und `"ok"`; bei Fehlern zusätzlich `"err"`.
* Nach jedem Start sendet das Gerät `@{"evt":"boot", "fw", "build", "target", "reset_reason", "models"}`.
  Kommt dieses Ereignis, während der Host auf eine Antwort wartet, meldet der Host einen
  **unerwarteten Neustart** (`DeviceResetDetected`, z. B. durch Watchdog, Exception oder
  Brown-out) zusammen mit den letzten Logzeilen.

| Befehl | Antwortfelder |
|---|---|
| `PING` | `pong`, `uptime_ms` |
| `INFO` | `fw`, `proto`, `build`, `target`, `chip`, `uid`, `framework`, `engine`, `cpu_mhz`, `has_cycles`, `free_heap`, `min_free_heap`, `arena`, `line_max`, `models`, `reset_reason`, `uptime_ms`, `inferences` |
| `MODELS` | `models: [{idx, name, in, out, layers, arena, params, macs, crc, tests}]` |
| `INFER <modell> <hex>` | `out` (hex, int8), `us`, `cycles`, `in_crc` (CRC32 der empfangenen Eingabe) |
| `BENCH <modell> [n=10] [warmup=1]` | `n`, `us_min/max/avg/total`, `cyc_min/max/avg`, `macs`, `stable`, `heap_before/after`, `min_free_heap` |
| `SELFTEST <modell>` | `passed`, `total`, `first_fail`, `crc_ok`, `us_total` (eingebettete Golden Vectors) |
| `VERIFY <modell>` | `crc`, `expected`, `match` (CRC der Gewichte, aus dem Flash gelesen), `us` |
| `MEM` | `free_heap`, `min_free_heap`, `arena`, `static_bufs` |
| `ECHO <hex>` | `len`, `data`, `crc` (Link-Test) |
| `RESET` | `resetting`, danach Neustart |

`<modell>` ist der Name oder Index. Zeilen, die länger als `line_max` sind, werden mit
`{"id":0,"ok":false,"err":"line too long"}` abgelehnt.

Beispiel:

```
#3 INFER can_ids_mlp 00112233…            (32 Bytes = 64 Hex-Zeichen)
@{"id":3,"ok":true,"model":"can_ids_mlp","out":"7f81","us":412,"cycles":32950,"in_crc":"1a2b3c4d"}
```
