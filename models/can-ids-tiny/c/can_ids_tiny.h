/*
 * can-ids-tiny: frame-level CAN intrusion detector for microcontrollers.
 *
 * Feed every received CAN frame to can_ids_tiny_process() in bus order. It returns 1 when the
 * frame raises an alarm: at least CAN_IDS_TINY_ALARM_K frames scored above the threshold within
 * CAN_IDS_TINY_ALARM_WINDOW_US (then alarms are held off for CAN_IDS_TINY_ALARM_HOLDOFF_US).
 * can_ids_tiny_score() gives the raw per-frame score: the share of trees voting "attack".
 *
 * Requires the generated files can_ids_tiny_model.h and can_ids_tiny_config.h (see pipeline.py export).
 */
#ifndef CAN_IDS_TINY_H
#define CAN_IDS_TINY_H

#include <stdint.h>

#include "msml_alarm.h"
#include "msml_can_features.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    msml_can_state_t features;
    msml_alarm_t alarm;
} can_ids_tiny_t;

void can_ids_tiny_init(can_ids_tiny_t *ids);

/* Returns the attack score of this frame (share of trees voting attack). */
float can_ids_tiny_score(can_ids_tiny_t *ids, int64_t ts_us, uint32_t can_id, uint8_t dlc,
                         const uint8_t data[8]);

/* Score the frame and update the alarm stage. Returns 1 if this frame raises an alarm.
 * score_out (optional) receives the frame score. */
int can_ids_tiny_process(can_ids_tiny_t *ids, int64_t ts_us, uint32_t can_id, uint8_t dlc,
                         const uint8_t data[8], float *score_out);

/* Score threshold chosen on validation data. */
float can_ids_tiny_threshold(void);

#ifdef __cplusplus
}
#endif

#endif /* CAN_IDS_TINY_H */
