/*
 * can-ids-tiny on-device benchmark.
 *
 * Replays recorded CAN frames (test_vectors.h) through the full detector: feature extraction
 * plus random forest. For every frame it measures the latency and checks that the score is
 * identical to the score computed on the host. Results are printed as one JSON line.
 * No CAN transceiver is needed.
 */
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "can_ids_tiny.h"
#include "esp_chip_info.h"
#include "esp_cpu.h"
#include "esp_heap_caps.h"
#include "esp_rom_sys.h"
#include "esp_system.h"
#include "esp_clk_tree.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "test_vectors.h"

static can_ids_tiny_t s_ids;
static uint32_t s_cycles[TV_N_FRAMES];

static int cmp_u32(const void *a, const void *b)
{
    uint32_t x = *(const uint32_t *)a, y = *(const uint32_t *)b;
    return (x > y) - (x < y);
}

static void run_once(int *mismatches, int *detected, int *attacks)
{
    can_ids_tiny_init(&s_ids);
    const float thr = can_ids_tiny_threshold();
    *mismatches = *detected = *attacks = 0;
    for (int i = 0; i < TV_N_FRAMES; i++) {
        const tv_frame_t *f = &tv_frames[i];
        uint32_t t0 = esp_cpu_get_cycle_count();
        float s = can_ids_tiny_score(&s_ids, f->ts_us, f->can_id, f->dlc, f->data);
        s_cycles[i] = esp_cpu_get_cycle_count() - t0;
        *mismatches += (s != tv_expected_score[i]);
        *attacks += f->label;
        *detected += f->label && (s >= thr);
    }
}

void app_main(void)
{
    esp_chip_info_t chip;
    esp_chip_info(&chip);
    uint32_t cpu_hz = 0;
    esp_clk_tree_src_get_freq_hz(SOC_MOD_CLK_CPU, ESP_CLK_TREE_SRC_FREQ_PRECISION_CACHED, &cpu_hz);

    int mismatches, detected, attacks;
    run_once(&mismatches, &detected, &attacks); /* warm-up: fill caches */
    run_once(&mismatches, &detected, &attacks);

    qsort(s_cycles, TV_N_FRAMES, sizeof(s_cycles[0]), cmp_u32);
    uint64_t sum = 0;
    for (int i = 0; i < TV_N_FRAMES; i++) {
        sum += s_cycles[i];
    }
    const float mhz = cpu_hz / 1e6f;
    /* Repeat the result so a serial monitor that connects late still sees it. */
    while (1) {
        printf("CAN_IDS_TINY_RESULT {\"target\":\"%s\",\"cpu_mhz\":%.0f,\"frames\":%d,"
               "\"score_mismatches\":%d,\"attack_frames\":%d,\"detected\":%d,"
               "\"latency_us\":{\"median\":%.2f,\"mean\":%.2f,\"p99\":%.2f,\"max\":%.2f},"
               "\"state_bytes\":%u,\"free_heap\":%" PRIu32 "}\n",
               CONFIG_IDF_TARGET, mhz, TV_N_FRAMES, mismatches, attacks, detected,
               s_cycles[TV_N_FRAMES / 2] / mhz, (float)sum / TV_N_FRAMES / mhz,
               s_cycles[(TV_N_FRAMES * 99) / 100] / mhz, s_cycles[TV_N_FRAMES - 1] / mhz,
               (unsigned)sizeof(s_ids), esp_get_free_heap_size());
        vTaskDelay(pdMS_TO_TICKS(5000));
    }
}
