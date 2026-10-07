#include <Arduino.h>


#define TV_STORAGE PROGMEM
#include "src/can_ids_tiny.h"
#include "src/test_vectors.h"

static can_ids_tiny_t s_ids;
static uint32_t s_cycles[TV_N_FRAMES];
static int s_mismatches, s_detected, s_attacks;
static uint32_t s_sum;

static void run_once()
{
    can_ids_tiny_init(&s_ids);
    const float thr = can_ids_tiny_threshold();
    s_mismatches = s_detected = s_attacks = 0;
    for (int i = 0; i < TV_N_FRAMES; i++) {
        tv_frame_t f;
        float expected;
        memcpy_P(&f, &tv_frames[i], sizeof(f));
        memcpy_P(&expected, &tv_expected_score[i], sizeof(expected));
        uint32_t t0 = ESP.getCycleCount();
        float s = can_ids_tiny_score(&s_ids, f.ts_us, f.can_id, f.dlc, f.data);
        s_cycles[i] = ESP.getCycleCount() - t0;
        s_mismatches += (s != expected);
        s_attacks += f.label;
        s_detected += f.label && (s >= thr);
        if ((i & 255) == 0) {
            yield(); /* keep the watchdog happy */
        }
    }
}

static int cmp_u32(const void *a, const void *b)
{
    uint32_t x = *(const uint32_t *)a, y = *(const uint32_t *)b;
    return (x > y) - (x < y);
}

void setup()
{
    Serial.begin(115200);
    delay(500);
    run_once(); /* warm-up: fill the flash cache */
    run_once();
    s_sum = 0;
    for (int i = 0; i < TV_N_FRAMES; i++) {
        s_sum += s_cycles[i];
    }
    qsort(s_cycles, TV_N_FRAMES, sizeof(s_cycles[0]), cmp_u32);
}

void loop()
{
    const float mhz = ESP.getCpuFreqMHz();
    Serial.printf("CAN_IDS_TINY_RESULT {\"target\":\"esp8266\",\"cpu_mhz\":%.0f,\"frames\":%d,"
                  "\"score_mismatches\":%d,\"attack_frames\":%d,\"detected\":%d,"
                  "\"latency_us\":{\"median\":%.2f,\"mean\":%.2f,\"p99\":%.2f,\"max\":%.2f},"
                  "\"state_bytes\":%u,\"free_heap\":%u}\n",
                  mhz, TV_N_FRAMES, s_mismatches, s_attacks, s_detected,
                  s_cycles[TV_N_FRAMES / 2] / mhz, (float)s_sum / TV_N_FRAMES / mhz,
                  s_cycles[(TV_N_FRAMES * 99) / 100] / mhz, s_cycles[TV_N_FRAMES - 1] / mhz,
                  (unsigned)sizeof(s_ids), (unsigned)ESP.getFreeHeap());
    delay(5000);
}
