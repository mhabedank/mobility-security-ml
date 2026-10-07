/*
 * HIL bench firmware for Arduino-compatible SoCs.
 * The portable logic lives in lib/benchapp, lib/microinfer and lib/modelzoo.
 */
#include <Arduino.h>

#include "benchapp.h"
#include "microinfer.h"
#include "model_zoo.h"

#ifndef HIL_SERIAL_BAUD
#define HIL_SERIAL_BAUD 115200
#endif

void hal_arduino_begin(uint32_t baud);

void setup()
{
    hal_arduino_begin(HIL_SERIAL_BAUD);
    delay(50);
    bench_init();
}

void loop()
{
    bench_poll();
}
