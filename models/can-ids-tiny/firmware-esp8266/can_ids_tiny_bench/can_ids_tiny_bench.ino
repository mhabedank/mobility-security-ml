/*
 * can-ids-tiny on-device benchmark for ESP8266 (Wemos D1 mini, NodeMCU, ...).
 *
 * Replays recorded CAN frames (stored in flash) through feature extraction and the random
 * forest, checks every score against the host result and prints one JSON line every 5 s.
 * No CAN transceiver is needed. Build with ../build.sh, which copies the C sources into src/.
 * The code lives in bench.cpp so the Arduino .ino preprocessing has nothing to rewrite.
 */
