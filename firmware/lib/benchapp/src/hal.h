/*
 * Hardware abstraction used by the bench application.
 *
 * Porting the bench to a new SoC = implementing these functions (see
 * firmware/src/hal_arduino.cpp for Arduino cores and firmware/native/hal_native.c
 * for the host simulator).
 */
#ifndef HIL_HAL_H
#define HIL_HAL_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Serial link to the HIL host. */
void hal_write(const char *data, size_t len);
int hal_read(void); /* next byte or -1 if none is pending */

/* Time. hal_cycles() returns 0 on cores without a cycle counter. */
uint32_t hal_micros(void);
uint32_t hal_millis(void);
uint32_t hal_cycles(void);
uint32_t hal_cpu_mhz(void);

/* Memory statistics in bytes (0 = unknown). */
uint32_t hal_free_heap(void);
uint32_t hal_min_free_heap(void);

/* Identification. */
const char *hal_target(void);       /* build target, e.g. "esp32s3" */
const char *hal_chip(void);         /* chip detected at runtime, e.g. "ESP32-S3 rev0" */
const char *hal_uid(void);          /* unique id (MAC, UID...), "" if unknown */
const char *hal_framework(void);    /* e.g. "arduino-esp32 2.0.17" */
const char *hal_reset_reason(void);

/* Housekeeping. */
void hal_yield(void); /* feed watchdogs / let the RTOS run */
void hal_reset(void); /* software reset, does not return */

#ifdef __cplusplus
}
#endif

#endif /* HIL_HAL_H */
