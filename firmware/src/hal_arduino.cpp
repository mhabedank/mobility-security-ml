/*
 * HAL for Arduino cores. One file, #ifdef'd per architecture:
 *
 *   ARDUINO_ARCH_ESP8266  ESP8266 / ESP8266MOD (ESP-12E/F, NodeMCU, Wemos D1 mini)
 *   ARDUINO_ARCH_ESP32    ESP32, ESP32-S2/S3 (Xtensa), ESP32-C3/C6/H2 (RISC-V)
 *   ARDUINO_ARCH_RP2040   RP2040 / RP2350 (arduino-pico core)
 *   ARDUINO_ARCH_STM32    STM32 (stm32duino)
 *   ARDUINO_ARCH_MBED     nRF52840 (Arduino Nano 33 BLE), RP2040 mbed
 *   anything else         generic fallback (micros() timing only)
 *
 * Adding another SoC: add a branch here (or rely on the fallback), add a
 * PlatformIO env in platformio.ini and a target entry in hil/targets.yaml.
 */
#include <Arduino.h>
#include <stdio.h>
#include <string.h>

#include "hal.h"

#ifndef HIL_TARGET
#define HIL_TARGET "arduino"
#endif

#if defined(ARDUINO_ARCH_ESP32)
#include <esp_system.h>
#if __has_include(<esp_arduino_version.h>)
#include <esp_arduino_version.h>
#endif
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#elif defined(ARDUINO_ARCH_RP2040)
#include <hardware/watchdog.h>
#include <pico/unique_id.h>
#endif

#if !defined(ARDUINO_ARCH_ESP8266) && !defined(ARDUINO_ARCH_ESP32) && !defined(ARDUINO_ARCH_RP2040) && \
    (defined(__ARM_ARCH_7M__) || defined(__ARM_ARCH_7EM__) || defined(__ARM_ARCH_8M_MAIN__))
#define HIL_ARM_DWT 1
#endif

static char s_chip[64];
static char s_uid[40];
static char s_framework[64];
static char s_reset_reason[32];
static uint32_t s_min_heap = 0xFFFFFFFFu;

static void track_heap(uint32_t free_now)
{
    if (free_now && free_now < s_min_heap) s_min_heap = free_now;
}

/* Called from setup() before bench_init(). */
void hal_arduino_begin(uint32_t baud)
{
#if defined(ARDUINO_ARCH_ESP8266) || defined(ARDUINO_ARCH_ESP32)
    Serial.setRxBufferSize(2048);
#endif
    Serial.begin(baud);

#if defined(HIL_ARM_DWT)
    CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
    DWT->CYCCNT = 0;
    DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;
#endif

#if defined(ARDUINO_ARCH_ESP8266)
    snprintf(s_chip, sizeof(s_chip), "ESP8266 flash=%luKB", (unsigned long)(ESP.getFlashChipRealSize() / 1024u));
    snprintf(s_uid, sizeof(s_uid), "%06lx", (unsigned long)ESP.getChipId());
    snprintf(s_framework, sizeof(s_framework), "arduino-esp8266 %s", ESP.getCoreVersion().c_str());
    snprintf(s_reset_reason, sizeof(s_reset_reason), "%s", ESP.getResetReason().c_str());
#elif defined(ARDUINO_ARCH_ESP32)
    snprintf(s_chip, sizeof(s_chip), "%s rev%d cores=%d", ESP.getChipModel(), (int)ESP.getChipRevision(),
             (int)ESP.getChipCores());
    uint64_t mac = ESP.getEfuseMac();
    snprintf(s_uid, sizeof(s_uid), "%04x%08lx", (unsigned)(mac >> 32), (unsigned long)(mac & 0xFFFFFFFFu));
#if defined(ESP_ARDUINO_VERSION_MAJOR)
    snprintf(s_framework, sizeof(s_framework), "arduino-esp32 %d.%d.%d idf %s", ESP_ARDUINO_VERSION_MAJOR,
             ESP_ARDUINO_VERSION_MINOR, ESP_ARDUINO_VERSION_PATCH, esp_get_idf_version());
#else
    snprintf(s_framework, sizeof(s_framework), "arduino-esp32 idf %s", esp_get_idf_version());
#endif
    const char *rr = "unknown";
    switch (esp_reset_reason()) {
    case ESP_RST_POWERON: rr = "power_on"; break;
    case ESP_RST_EXT: rr = "external"; break;
    case ESP_RST_SW: rr = "software"; break;
    case ESP_RST_PANIC: rr = "panic"; break;
    case ESP_RST_INT_WDT: rr = "int_wdt"; break;
    case ESP_RST_TASK_WDT: rr = "task_wdt"; break;
    case ESP_RST_WDT: rr = "wdt"; break;
    case ESP_RST_DEEPSLEEP: rr = "deep_sleep"; break;
    case ESP_RST_BROWNOUT: rr = "brownout"; break;
    default: break;
    }
    snprintf(s_reset_reason, sizeof(s_reset_reason), "%s", rr);
#elif defined(ARDUINO_ARCH_RP2040)
#if defined(PICO_RP2350)
    snprintf(s_chip, sizeof(s_chip), "RP2350");
#else
    snprintf(s_chip, sizeof(s_chip), "RP2040");
#endif
    pico_get_unique_board_id_string(s_uid, sizeof(s_uid));
#if defined(ARDUINO_PICO_VERSION_STR)
    snprintf(s_framework, sizeof(s_framework), "arduino-pico %s", ARDUINO_PICO_VERSION_STR);
#else
    snprintf(s_framework, sizeof(s_framework), "arduino-pico");
#endif
    snprintf(s_reset_reason, sizeof(s_reset_reason), "%s", watchdog_caused_reboot() ? "watchdog" : "power_on");
#elif defined(ARDUINO_ARCH_STM32)
    snprintf(s_chip, sizeof(s_chip), "STM32 dev=0x%03lx rev=0x%04lx", (unsigned long)HAL_GetDEVID(),
             (unsigned long)HAL_GetREVID());
    snprintf(s_uid, sizeof(s_uid), "%08lx%08lx%08lx", (unsigned long)HAL_GetUIDw0(), (unsigned long)HAL_GetUIDw1(),
             (unsigned long)HAL_GetUIDw2());
#if defined(STM32_CORE_VERSION_MAJOR)
    snprintf(s_framework, sizeof(s_framework), "stm32duino %d.%d.%d", STM32_CORE_VERSION_MAJOR,
             STM32_CORE_VERSION_MINOR, STM32_CORE_VERSION_PATCH);
#else
    snprintf(s_framework, sizeof(s_framework), "stm32duino");
#endif
    snprintf(s_reset_reason, sizeof(s_reset_reason), "unknown");
#elif defined(ARDUINO_ARCH_MBED)
#if defined(ARDUINO_ARCH_NRF52840) || defined(NRF52840_XXAA)
    snprintf(s_chip, sizeof(s_chip), "nRF52840");
#else
    snprintf(s_chip, sizeof(s_chip), "mbed");
#endif
    snprintf(s_framework, sizeof(s_framework), "arduino-mbed");
    snprintf(s_reset_reason, sizeof(s_reset_reason), "unknown");
#else
    snprintf(s_chip, sizeof(s_chip), "unknown");
    snprintf(s_framework, sizeof(s_framework), "arduino");
    snprintf(s_reset_reason, sizeof(s_reset_reason), "unknown");
#endif
    track_heap(hal_free_heap());
}

extern "C" {

void hal_write(const char *data, size_t len)
{
    Serial.write(reinterpret_cast<const uint8_t *>(data), len);
}

int hal_read(void)
{
    return Serial.available() > 0 ? Serial.read() : -1;
}

uint32_t hal_micros(void) { return micros(); }
uint32_t hal_millis(void) { return millis(); }

uint32_t hal_cycles(void)
{
#if defined(ARDUINO_ARCH_ESP8266) || defined(ARDUINO_ARCH_ESP32)
    return ESP.getCycleCount();
#elif defined(ARDUINO_ARCH_RP2040)
    return rp2040.getCycleCount();
#elif defined(HIL_ARM_DWT)
    return DWT->CYCCNT;
#else
    return 0;
#endif
}

uint32_t hal_cpu_mhz(void)
{
#if defined(ARDUINO_ARCH_ESP8266)
    return ESP.getCpuFreqMHz();
#elif defined(ARDUINO_ARCH_ESP32)
    return getCpuFrequencyMhz();
#elif defined(ARDUINO_ARCH_RP2040)
    return rp2040.f_cpu() / 1000000u;
#elif defined(ARDUINO_ARCH_STM32) || defined(ARDUINO_ARCH_MBED)
    return SystemCoreClock / 1000000u;
#elif defined(F_CPU)
    return (uint32_t)(F_CPU / 1000000u);
#else
    return 0;
#endif
}

uint32_t hal_free_heap(void)
{
    uint32_t v = 0;
#if defined(ARDUINO_ARCH_ESP8266) || defined(ARDUINO_ARCH_ESP32)
    v = ESP.getFreeHeap();
#elif defined(ARDUINO_ARCH_RP2040)
    v = (uint32_t)rp2040.getFreeHeap();
#endif
    track_heap(v);
    return v;
}

uint32_t hal_min_free_heap(void)
{
#if defined(ARDUINO_ARCH_ESP32)
    return ESP.getMinFreeHeap();
#else
    return s_min_heap == 0xFFFFFFFFu ? 0 : s_min_heap;
#endif
}

const char *hal_target(void) { return HIL_TARGET; }
const char *hal_chip(void) { return s_chip; }
const char *hal_uid(void) { return s_uid; }
const char *hal_framework(void) { return s_framework; }
const char *hal_reset_reason(void) { return s_reset_reason; }

void hal_yield(void)
{
#if defined(ARDUINO_ARCH_ESP8266)
    ESP.wdtFeed();
    yield();
#elif defined(ARDUINO_ARCH_ESP32)
    /* Let the idle task run now and then, otherwise the task watchdog fires on
     * single-core chips (C3) during long benchmarks. */
    static uint32_t last = 0;
    if (millis() - last > 100u) {
        vTaskDelay(1);
        last = millis();
    }
#else
    yield();
#endif
    track_heap(hal_free_heap());
}

void hal_reset(void)
{
    Serial.flush();
#if defined(ARDUINO_ARCH_ESP8266) || defined(ARDUINO_ARCH_ESP32)
    ESP.restart();
#elif defined(ARDUINO_ARCH_RP2040)
    rp2040.reboot();
#elif defined(ARDUINO_ARCH_STM32) || defined(ARDUINO_ARCH_MBED) || defined(HIL_ARM_DWT)
    NVIC_SystemReset();
#endif
    for (;;) {
        /* no software reset available: wait for the host to power-cycle us */
    }
}

} /* extern "C" */
