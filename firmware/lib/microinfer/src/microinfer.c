/*
 * microinfer - see microinfer.h.
 *
 * Kernels are intentionally straightforward reference implementations; the
 * HIL bench measures how fast *the same code* runs on each SoC and checks
 * that every SoC produces bit-identical results.
 */
#include "microinfer.h"

#include <string.h>

/* ---- fixed-point helpers (TFLite reference semantics) ------------------ */

static int32_t mi_saturating_rounding_doubling_high_mul(int32_t a, int32_t b)
{
    if (a == b && a == INT32_MIN) {
        return INT32_MAX;
    }
    int64_t ab = (int64_t)a * (int64_t)b;
    int64_t nudge = ab >= 0 ? (1LL << 30) : (1LL - (1LL << 30));
    /* C division truncates toward zero, exactly as in gemmlowp. */
    return (int32_t)((ab + nudge) / (1LL << 31));
}

static int32_t mi_rounding_divide_by_pot(int32_t x, int exponent)
{
    const int32_t mask = (int32_t)((1LL << exponent) - 1);
    const int32_t remainder = x & mask;
    const int32_t threshold = (mask >> 1) + ((x < 0) ? 1 : 0);
    return (x >> exponent) + ((remainder > threshold) ? 1 : 0);
}

int32_t mi_multiply_by_quantized_multiplier(int32_t x, int32_t mult, int shift)
{
    const int left_shift = shift > 0 ? shift : 0;
    const int right_shift = shift > 0 ? 0 : -shift;
    return mi_rounding_divide_by_pot(
        mi_saturating_rounding_doubling_high_mul((int32_t)((uint32_t)x << left_shift), mult),
        right_shift);
}

/* Single-rounding variant (TFLITE_SINGLE_ROUNDING), used by TFLite's
 * FULLY_CONNECTED kernels. */
int32_t mi_multiply_by_quantized_multiplier_single(int32_t x, int32_t mult, int shift)
{
    const int total_shift = 31 - shift;
    const int64_t round = (int64_t)1 << (total_shift - 1);
    return (int32_t)(((int64_t)x * mult + round) >> total_shift);
}

static int8_t mi_requantize(const mi_layer_t *l, int32_t acc, uint16_t ch)
{
    const uint16_t idx = l->n_mult > 1 ? ch : 0;
    const int32_t m = MI_RD_I32(&l->mult[idx]);
    const int s = (int)MI_RD_I8(&l->shift[idx]);
    int32_t v = (l->flags & MI_FLAG_SINGLE_ROUNDING) ? mi_multiply_by_quantized_multiplier_single(acc, m, s)
                                                     : mi_multiply_by_quantized_multiplier(acc, m, s);
    v += l->out_zp;
    if (v < l->act_min) v = l->act_min;
    if (v > l->act_max) v = l->act_max;
    return (int8_t)v;
}

static int32_t mi_bias(const mi_layer_t *l, uint16_t ch)
{
    return l->bias ? MI_RD_I32(&l->bias[ch]) : 0;
}

/* ---- kernels ------------------------------------------------------------ */

static void mi_dense(const mi_layer_t *l, const int8_t *in, int8_t *out)
{
    const int32_t in_off = -l->in_zp;
    for (uint16_t o = 0; o < l->out_c; o++) {
        const int8_t *w = l->weights + (uint32_t)o * l->in_c;
        int32_t acc = mi_bias(l, o);
        for (uint16_t i = 0; i < l->in_c; i++) {
            acc += ((int32_t)in[i] + in_off) * (int32_t)MI_RD_I8(&w[i]);
        }
        out[o] = mi_requantize(l, acc, o);
    }
}

static void mi_conv2d(const mi_layer_t *l, const int8_t *in, int8_t *out)
{
    const int32_t in_off = -l->in_zp;
    const uint32_t kstride = (uint32_t)l->k_h * l->k_w * l->in_c;
    for (uint16_t oy = 0; oy < l->out_h; oy++) {
        for (uint16_t ox = 0; ox < l->out_w; ox++) {
            const int32_t y0 = (int32_t)oy * l->stride_h - l->pad_t;
            const int32_t x0 = (int32_t)ox * l->stride_w - l->pad_l;
            for (uint16_t oc = 0; oc < l->out_c; oc++) {
                const int8_t *w = l->weights + (uint32_t)oc * kstride;
                int32_t acc = mi_bias(l, oc);
                for (uint8_t ky = 0; ky < l->k_h; ky++) {
                    const int32_t iy = y0 + ky;
                    if (iy < 0 || iy >= (int32_t)l->in_h) continue;
                    for (uint8_t kx = 0; kx < l->k_w; kx++) {
                        const int32_t ix = x0 + kx;
                        if (ix < 0 || ix >= (int32_t)l->in_w) continue;
                        const int8_t *px = in + ((uint32_t)iy * l->in_w + (uint32_t)ix) * l->in_c;
                        const int8_t *wk = w + ((uint32_t)ky * l->k_w + kx) * l->in_c;
                        for (uint16_t ic = 0; ic < l->in_c; ic++) {
                            acc += ((int32_t)px[ic] + in_off) * (int32_t)MI_RD_I8(&wk[ic]);
                        }
                    }
                }
                out[((uint32_t)oy * l->out_w + ox) * l->out_c + oc] = mi_requantize(l, acc, oc);
            }
        }
    }
}

static void mi_dwconv2d(const mi_layer_t *l, const int8_t *in, int8_t *out)
{
    const int32_t in_off = -l->in_zp;
    const uint16_t depth_mult = l->out_c / l->in_c;
    for (uint16_t oy = 0; oy < l->out_h; oy++) {
        for (uint16_t ox = 0; ox < l->out_w; ox++) {
            const int32_t y0 = (int32_t)oy * l->stride_h - l->pad_t;
            const int32_t x0 = (int32_t)ox * l->stride_w - l->pad_l;
            for (uint16_t oc = 0; oc < l->out_c; oc++) {
                const uint16_t ic = oc / depth_mult;
                int32_t acc = mi_bias(l, oc);
                for (uint8_t ky = 0; ky < l->k_h; ky++) {
                    const int32_t iy = y0 + ky;
                    if (iy < 0 || iy >= (int32_t)l->in_h) continue;
                    for (uint8_t kx = 0; kx < l->k_w; kx++) {
                        const int32_t ix = x0 + kx;
                        if (ix < 0 || ix >= (int32_t)l->in_w) continue;
                        const int32_t v = in[((uint32_t)iy * l->in_w + (uint32_t)ix) * l->in_c + ic];
                        const int32_t w = MI_RD_I8(&l->weights[((uint32_t)ky * l->k_w + kx) * l->out_c + oc]);
                        acc += (v + in_off) * w;
                    }
                }
                out[((uint32_t)oy * l->out_w + ox) * l->out_c + oc] = mi_requantize(l, acc, oc);
            }
        }
    }
}

static void mi_pool2d(const mi_layer_t *l, const int8_t *in, int8_t *out, int is_max)
{
    for (uint16_t oy = 0; oy < l->out_h; oy++) {
        for (uint16_t ox = 0; ox < l->out_w; ox++) {
            const int32_t y0 = (int32_t)oy * l->stride_h - l->pad_t;
            const int32_t x0 = (int32_t)ox * l->stride_w - l->pad_l;
            for (uint16_t c = 0; c < l->out_c; c++) {
                int32_t acc = is_max ? -128 : 0;
                int32_t count = 0;
                for (uint8_t ky = 0; ky < l->k_h; ky++) {
                    const int32_t iy = y0 + ky;
                    if (iy < 0 || iy >= (int32_t)l->in_h) continue;
                    for (uint8_t kx = 0; kx < l->k_w; kx++) {
                        const int32_t ix = x0 + kx;
                        if (ix < 0 || ix >= (int32_t)l->in_w) continue;
                        const int32_t v = in[((uint32_t)iy * l->in_w + (uint32_t)ix) * l->in_c + c];
                        if (is_max) {
                            if (v > acc) acc = v;
                        } else {
                            acc += v;
                        }
                        count++;
                    }
                }
                if (!is_max) {
                    if (count == 0) count = 1;
                    acc = acc > 0 ? (acc + count / 2) / count : (acc - count / 2) / count;
                }
                if (acc < l->act_min) acc = l->act_min;
                if (acc > l->act_max) acc = l->act_max;
                out[((uint32_t)oy * l->out_w + ox) * l->out_c + c] = (int8_t)acc;
            }
        }
    }
}

/* ---- graph execution ---------------------------------------------------- */

int mi_invoke(const mi_model_t *model, const int8_t *input, int8_t *output,
              int8_t *arena, size_t arena_size)
{
    if (arena_size < model->arena_size) {
        return MI_ERR_ARENA;
    }
    /* Sequential graph: ping-pong between the two halves of the arena. */
    const size_t half = model->arena_size / 2;
    int8_t *cur = arena;
    int8_t *nxt = arena + half;
    memcpy(cur, input, model->in_size);

    for (uint16_t i = 0; i < model->n_layers; i++) {
        const mi_layer_t *l = &model->layers[i];
        switch (l->op) {
        case MI_OP_DENSE:
            mi_dense(l, cur, nxt);
            break;
        case MI_OP_CONV2D:
            mi_conv2d(l, cur, nxt);
            break;
        case MI_OP_DWCONV2D:
            mi_dwconv2d(l, cur, nxt);
            break;
        case MI_OP_MAXPOOL2D:
            mi_pool2d(l, cur, nxt, 1);
            break;
        case MI_OP_AVGPOOL2D:
            mi_pool2d(l, cur, nxt, 0);
            break;
        case MI_OP_RESHAPE:
            continue; /* HWC flatten is a no-op */
        default:
            return MI_ERR_OP;
        }
        int8_t *t = cur;
        cur = nxt;
        nxt = t;
    }
    memcpy(output, cur, model->out_size);
    return MI_OK;
}

/* ---- integrity ---------------------------------------------------------- */

uint32_t mi_crc32_update(uint32_t crc, const uint8_t *data, size_t len)
{
    crc = ~crc;
    for (size_t i = 0; i < len; i++) {
        crc ^= data[i];
        for (int k = 0; k < 8; k++) {
            crc = (crc >> 1) ^ (0xEDB88320u & (0u - (crc & 1u)));
        }
    }
    return ~crc;
}

static uint32_t mi_crc_i8_const(uint32_t crc, const int8_t *p, uint32_t n)
{
    for (uint32_t i = 0; i < n; i++) {
        uint8_t b = (uint8_t)MI_RD_I8(&p[i]);
        crc = mi_crc32_update(crc, &b, 1);
    }
    return crc;
}

static uint32_t mi_crc_i32_const(uint32_t crc, const int32_t *p, uint32_t n)
{
    for (uint32_t i = 0; i < n; i++) {
        uint32_t v = (uint32_t)MI_RD_I32(&p[i]);
        uint8_t b[4] = {(uint8_t)v, (uint8_t)(v >> 8), (uint8_t)(v >> 16), (uint8_t)(v >> 24)};
        crc = mi_crc32_update(crc, b, 4);
    }
    return crc;
}

static uint32_t mi_weight_count(const mi_layer_t *l)
{
    switch (l->op) {
    case MI_OP_DENSE:
        return (uint32_t)l->out_c * l->in_c;
    case MI_OP_CONV2D:
        return (uint32_t)l->out_c * l->k_h * l->k_w * l->in_c;
    case MI_OP_DWCONV2D:
        return (uint32_t)l->k_h * l->k_w * l->out_c;
    default:
        return 0;
    }
}

uint32_t mi_model_crc32(const mi_model_t *model)
{
    uint32_t crc = 0;
    for (uint16_t i = 0; i < model->n_layers; i++) {
        const mi_layer_t *l = &model->layers[i];
        const uint32_t nw = mi_weight_count(l);
        if (nw == 0) continue;
        crc = mi_crc_i8_const(crc, l->weights, nw);
        if (l->bias) crc = mi_crc_i32_const(crc, l->bias, l->out_c);
        crc = mi_crc_i32_const(crc, l->mult, l->n_mult);
        crc = mi_crc_i8_const(crc, l->shift, l->n_mult);
    }
    return crc;
}
