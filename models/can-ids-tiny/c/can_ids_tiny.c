#include "can_ids_tiny.h"

#include "can_ids_tiny_config.h"
#include "can_ids_tiny_model.h"

/* Defaults for configs generated before the alarm stage existed: one alarm per flagged frame,
 * at most one per second. */
#ifndef CAN_IDS_TINY_ALARM_K
#define CAN_IDS_TINY_ALARM_K 1
#define CAN_IDS_TINY_ALARM_WINDOW_US 0
#define CAN_IDS_TINY_ALARM_HOLDOFF_US 1000000
#endif

void can_ids_tiny_init(can_ids_tiny_t *ids)
{
    msml_can_reset(&ids->features);
    msml_alarm_init(&ids->alarm, CAN_IDS_TINY_ALARM_K, CAN_IDS_TINY_ALARM_WINDOW_US,
                    CAN_IDS_TINY_ALARM_HOLDOFF_US);
}

float can_ids_tiny_score(can_ids_tiny_t *ids, int64_t ts_us, uint32_t can_id, uint8_t dlc,
                         const uint8_t data[8])
{
    float all[MSML_CAN_N_FEATURES];
    float x[CAN_IDS_TINY_N_INPUTS];
    float proba[2];

    msml_can_update(&ids->features, ts_us, can_id, dlc, data, all);
    for (int i = 0; i < CAN_IDS_TINY_N_INPUTS; i++) {
        x[i] = all[can_ids_tiny_input_index[i]];
    }
    can_ids_tiny_model_predict_proba(x, CAN_IDS_TINY_N_INPUTS, proba, 2);
    return proba[1];
}

int can_ids_tiny_process(can_ids_tiny_t *ids, int64_t ts_us, uint32_t can_id, uint8_t dlc,
                         const uint8_t data[8], float *score_out)
{
    const float s = can_ids_tiny_score(ids, ts_us, can_id, dlc, data);
    if (score_out != NULL) {
        *score_out = s;
    }
    return msml_alarm_update(&ids->alarm, ts_us, s >= CAN_IDS_TINY_THRESHOLD);
}

float can_ids_tiny_threshold(void)
{
    return CAN_IDS_TINY_THRESHOLD;
}
