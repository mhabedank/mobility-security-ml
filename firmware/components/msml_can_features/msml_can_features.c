#include "msml_can_features.h"

#include <stdlib.h>
#include <string.h>

#define CAP_DT_MS 1000.0f
#define CAP_RATIO 100.0f
#define CAP_ID_COUNT 1000u
#define CAP_WARMUP 5000u
#define ALPHA_ID 0.0625f      /* 1/16 */
#define ALPHA_BUS 0.03125f    /* 1/32 */
#define ALPHA_NEW_ID 0.015625f /* 1/64 */

static inline float minf(float a, float b) { return a < b ? a : b; }
static inline float maxf(float a, float b) { return a > b ? a : b; }

static inline uint8_t popcount8(uint8_t x)
{
    x = x - ((x >> 1) & 0x55);
    x = (x & 0x33) + ((x >> 2) & 0x33);
    return (uint8_t)((x + (x >> 4)) & 0x0F);
}

void msml_can_reset(msml_can_state_t *s)
{
    memset(s, 0, sizeof(*s));
    memset(s->slot_of, MSML_CAN_NO_SLOT, sizeof(s->slot_of));
}

/* Slot for this identifier; allocates one (evicting the least recently seen) if needed. */
static msml_can_id_state_t *slot_for(msml_can_state_t *s, uint16_t id)
{
    uint8_t k = s->slot_of[id];
    if (k != MSML_CAN_NO_SLOT) {
        return &s->slots[k];
    }
    if (s->slots_used < MSML_CAN_N_SLOTS) {
        k = (uint8_t)s->slots_used++;
    } else {
        k = 0;
        for (uint16_t i = 1; i < MSML_CAN_N_SLOTS; i++) {
            if (s->slots[i].last_us < s->slots[k].last_us) {
                k = (uint8_t)i;
            }
        }
        s->slot_of[s->slots[k].can_id] = MSML_CAN_NO_SLOT;
    }
    msml_can_id_state_t *e = &s->slots[k];
    memset(e, 0, sizeof(*e));
    e->can_id = id;
    s->slot_of[id] = k;
    return e;
}

void msml_can_update(msml_can_state_t *s, int64_t ts_us, uint32_t can_id, uint8_t dlc,
                     const uint8_t data[8], float out[MSML_CAN_N_FEATURES])
{
    msml_can_id_state_t *e = slot_for(s, (uint16_t)(can_id & (MSML_CAN_N_IDS - 1)));
    const int first = (e->count == 0);

    /* Per-ID timing. */
    float dt_id = CAP_DT_MS;
    float ratio = 1.0f;
    if (!first) {
        dt_id = minf((float)(ts_us - e->last_us) / 1000.0f, CAP_DT_MS);
        if (e->count >= 2) {
            ratio = minf(dt_id / maxf(e->ewma_dt_ms, 0.01f), CAP_RATIO);
        }
    }

    /* Bus timing. */
    float dt_bus = CAP_DT_MS;
    if (s->frames > 0) {
        dt_bus = minf((float)(ts_us - s->last_bus_us) / 1000.0f, CAP_DT_MS);
        if (s->frames == 1) {
            s->ewma_bus_dt_ms = dt_bus;
        } else {
            s->ewma_bus_dt_ms += ALPHA_BUS * (dt_bus - s->ewma_bus_dt_ms);
        }
    }
    s->new_id_rate += ALPHA_NEW_ID * ((first ? 1.0f : 0.0f) - s->new_id_rate);

    /* Payload change vs previous frame of this ID. */
    int ham = 0, changed = 0, dlc_changed = 0;
    if (!first) {
        for (int i = 0; i < 8; i++) {
            uint8_t x = (uint8_t)(data[i] ^ e->data[i]);
            ham += popcount8(x);
            changed += (x != 0);
        }
        dlc_changed = (dlc != e->dlc);
    }
    const float ham_ratio = (float)ham / (e->ewma_ham + 1.0f);

    out[MSML_F_DT_ID_MS] = dt_id;
    out[MSML_F_DT_RATIO] = ratio;
    out[MSML_F_DT_BUS_MS] = dt_bus;
    out[MSML_F_BUS_DT_EWMA_MS] = s->frames > 0 ? s->ewma_bus_dt_ms : CAP_DT_MS;
    out[MSML_F_ID_COUNT] = (float)(e->count < CAP_ID_COUNT ? e->count : CAP_ID_COUNT);
    out[MSML_F_WARMUP] = (float)(s->frames < CAP_WARMUP ? s->frames : CAP_WARMUP);
    out[MSML_F_NEW_ID_RATE] = s->new_id_rate;
    out[MSML_F_DLC] = (float)dlc;
    out[MSML_F_DLC_CHANGED] = (float)dlc_changed;
    out[MSML_F_HAMMING] = (float)ham;
    out[MSML_F_BYTES_CHANGED] = (float)changed;
    out[MSML_F_HAM_RATIO] = ham_ratio;
    out[MSML_F_CAN_ID] = (float)can_id;

    /* State update. */
    if (!first) {
        if (e->count == 1) {
            e->ewma_dt_ms = dt_id;
        } else {
            e->ewma_dt_ms += ALPHA_ID * (dt_id - e->ewma_dt_ms);
        }
        e->ewma_ham += ALPHA_ID * ((float)ham - e->ewma_ham);
    }
    if (e->count < UINT16_MAX) {
        e->count++;
    }
    e->last_us = ts_us;
    e->dlc = dlc;
    memcpy(e->data, data, 8);
    s->last_bus_us = ts_us;
    s->frames++;
}

int msml_can_extract_batch(const int64_t *ts_us, const uint16_t *can_id, const uint8_t *dlc,
                           const uint8_t *data, size_t n, float *out)
{
    msml_can_state_t *s = (msml_can_state_t *)malloc(sizeof(*s));
    if (s == NULL) {
        return -1;
    }
    msml_can_reset(s);
    for (size_t i = 0; i < n; i++) {
        msml_can_update(s, ts_us[i], can_id[i], dlc[i], &data[i * 8], &out[i * MSML_CAN_N_FEATURES]);
    }
    free(s);
    return 0;
}
