/*
 * Streaming per-frame features for CAN intrusion detection.
 *
 * The same C code runs on the host (called from Python via ctypes for training and
 * evaluation) and on the microcontroller, so training and on-device features are identical.
 *
 * All features depend only on the frame itself and on what was seen *before* it on the bus.
 * They do not use vehicle-specific knowledge (no DBC, no ID allow-list), so a model can be
 * evaluated on vehicles it was not trained on.
 *
 * Memory: per-ID state for up to MSML_CAN_N_SLOTS identifiers at a time (about 10 KB in total).
 * When a new ID arrives and all slots are taken, the ID seen the fewest times is evicted. Real
 * vehicles use far fewer IDs per bus; eviction only happens under fuzzing or ID scanning.
 *
 * Limits: 11-bit (standard) identifiers only; extended IDs are folded into the 11-bit range.
 * Build with -ffp-contract=off so float results match between host and MCU.
 */
#ifndef MSML_CAN_FEATURES_H
#define MSML_CAN_FEATURES_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define MSML_CAN_N_IDS 2048     /* 11-bit identifier space */
#define MSML_CAN_N_SLOTS 255    /* identifiers tracked at the same time */
#define MSML_CAN_NO_SLOT 0xFF
#define MSML_CAN_N_FEATURES 13

/* Feature indices (keep in sync with msml/can/features.py: FEATURE_NAMES). */
enum {
    MSML_F_DT_ID_MS = 0,     /* time since previous frame with the same ID (ms, capped) */
    MSML_F_DT_RATIO,         /* dt_id / running mean period of this ID (before update) */
    MSML_F_DT_BUS_MS,        /* time since previous frame of any ID (ms, capped) */
    MSML_F_BUS_DT_EWMA_MS,   /* running mean of dt_bus, a bus-load proxy */
    MSML_F_ID_COUNT,         /* frames seen with this ID before (capped) */
    MSML_F_WARMUP,           /* frames seen on the bus before (capped); lets the model discount start-up */
    MSML_F_NEW_ID_RATE,      /* running share of frames that carry a never-seen ID */
    MSML_F_DLC,
    MSML_F_DLC_CHANGED,      /* DLC differs from the previous frame of this ID */
    MSML_F_HAMMING,          /* bit flips vs previous payload of this ID */
    MSML_F_BYTES_CHANGED,    /* changed bytes vs previous payload of this ID */
    MSML_F_HAM_RATIO,        /* hamming / (running mean hamming of this ID + 1) */
    MSML_F_CAN_ID,           /* raw identifier (arbitration priority) */
};

typedef struct {
    int64_t last_us;
    float ewma_dt_ms;
    float ewma_ham;
    uint16_t can_id;
    uint16_t count;
    uint8_t dlc;
    uint8_t data[8];
} msml_can_id_state_t;

typedef struct {
    msml_can_id_state_t slots[MSML_CAN_N_SLOTS];
    uint8_t slot_of[MSML_CAN_N_IDS]; /* identifier -> slot index, or MSML_CAN_NO_SLOT */
    uint16_t slots_used;
    int64_t last_bus_us;
    float ewma_bus_dt_ms;
    float new_id_rate;
    uint32_t frames;
} msml_can_state_t;

void msml_can_reset(msml_can_state_t *s);

/* Update the state with one frame and write MSML_CAN_N_FEATURES floats to out.
 * data must point to 8 bytes; bytes beyond dlc must be zero. */
void msml_can_update(msml_can_state_t *s, int64_t ts_us, uint32_t can_id, uint8_t dlc,
                     const uint8_t data[8], float out[MSML_CAN_N_FEATURES]);

/* Host helper: reset, then process n frames. data is n*8 bytes, out is n*MSML_CAN_N_FEATURES.
 * Returns 0 on success, -1 if the state could not be allocated. */
int msml_can_extract_batch(const int64_t *ts_us, const uint16_t *can_id, const uint8_t *dlc,
                           const uint8_t *data, size_t n, float *out);

#ifdef __cplusplus
}
#endif

#endif /* MSML_CAN_FEATURES_H */
