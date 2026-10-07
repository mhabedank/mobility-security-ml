#include "msml_alarm.h"

#include <string.h>

void msml_alarm_init(msml_alarm_t *a, unsigned k, int64_t window_us, int64_t holdoff_us)
{
    memset(a, 0, sizeof(*a));
    if (k < 1) {
        k = 1;
    }
    if (k > MSML_ALARM_MAX_K) {
        k = MSML_ALARM_MAX_K;
    }
    a->k = (uint8_t)k;
    a->window_us = window_us;
    a->holdoff_us = holdoff_us;
}

int msml_alarm_update(msml_alarm_t *a, int64_t ts_us, int flagged)
{
    if (!flagged) {
        return 0;
    }
    a->flagged_us[a->head] = ts_us;
    a->head = (uint8_t)((a->head + 1) % a->k);
    if (a->filled < a->k) {
        a->filled++;
    }
    if (a->filled < a->k) {
        return 0;
    }
    /* After the write, head points at the oldest of the last k flagged frames. */
    const int64_t oldest = a->flagged_us[a->head];
    if (ts_us - oldest > a->window_us) {
        return 0;
    }
    if (a->has_alarmed && ts_us - a->last_alarm_us < a->holdoff_us) {
        return 0;
    }
    a->has_alarmed = 1;
    a->last_alarm_us = ts_us;
    return 1;
}

void msml_alarm_batch(const int64_t *ts_us, const uint8_t *flagged, size_t n, unsigned k,
                      int64_t window_us, int64_t holdoff_us, uint8_t *alarm)
{
    msml_alarm_t a;
    msml_alarm_init(&a, k, window_us, holdoff_us);
    for (size_t i = 0; i < n; i++) {
        alarm[i] = (uint8_t)msml_alarm_update(&a, ts_us[i], flagged[i]);
    }
}
