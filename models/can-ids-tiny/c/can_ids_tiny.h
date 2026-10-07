/*
 * can-ids-tiny: frame-level CAN intrusion detector for microcontrollers.
 *
 * Feed every received CAN frame to can_ids_tiny_score() in bus order. It returns the share of
 * trees that vote "attack" (0..1); compare it with CAN_IDS_TINY_THRESHOLD.
 *
 * Requires the generated files can_ids_tiny_model.h and can_ids_tiny_config.h (see pipeline.py export).
 */
#ifndef CAN_IDS_TINY_H
#define CAN_IDS_TINY_H

#include <stdint.h>

#include "msml_can_features.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    msml_can_state_t features;
} can_ids_tiny_t;

void can_ids_tiny_init(can_ids_tiny_t *ids);

/* Returns the attack score of this frame (share of trees voting attack). */
float can_ids_tiny_score(can_ids_tiny_t *ids, int64_t ts_us, uint32_t can_id, uint8_t dlc,
                         const uint8_t data[8]);

/* Score threshold chosen on validation data. */
float can_ids_tiny_threshold(void);

#ifdef __cplusplus
}
#endif

#endif /* CAN_IDS_TINY_H */
