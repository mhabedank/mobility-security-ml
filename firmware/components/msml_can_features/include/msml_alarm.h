/*
 * Alarm aggregation for frame-level detectors.
 *
 * A detector flags single frames; an alarm is raised when at least k flagged frames fall within
 * window_us. After an alarm, further alarms are suppressed for holdoff_us. This is the kind of
 * qualification an IDS manager (e.g. AUTOSAR IdsM) applies before reporting a security event.
 */
#ifndef MSML_ALARM_H
#define MSML_ALARM_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define MSML_ALARM_MAX_K 16

typedef struct {
    int64_t flagged_us[MSML_ALARM_MAX_K]; /* ring buffer of the last k flagged timestamps */
    uint8_t head;
    uint8_t filled;
    uint8_t k;
    int64_t window_us;
    int64_t holdoff_us;
    int64_t last_alarm_us;
    uint8_t has_alarmed;
} msml_alarm_t;

/* k is clamped to 1..MSML_ALARM_MAX_K. */
void msml_alarm_init(msml_alarm_t *a, unsigned k, int64_t window_us, int64_t holdoff_us);

/* Feed one frame decision; returns 1 if this frame raises an alarm. */
int msml_alarm_update(msml_alarm_t *a, int64_t ts_us, int flagged);

/* Host helper: run over n frames, writing 0/1 per frame to alarm. */
void msml_alarm_batch(const int64_t *ts_us, const uint8_t *flagged, size_t n, unsigned k,
                      int64_t window_us, int64_t holdoff_us, uint8_t *alarm);

#ifdef __cplusplus
}
#endif

#endif /* MSML_ALARM_H */
