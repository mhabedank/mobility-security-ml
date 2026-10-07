#include "can_ids_tiny.h"

#include "can_ids_tiny_config.h"
#include "can_ids_tiny_model.h"

void can_ids_tiny_init(can_ids_tiny_t *ids)
{
    msml_can_reset(&ids->features);
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

float can_ids_tiny_threshold(void)
{
    return CAN_IDS_TINY_THRESHOLD;
}
