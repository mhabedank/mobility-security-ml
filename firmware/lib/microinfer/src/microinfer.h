/*
 * microinfer - tiny, portable int8 inference engine for HIL benchmarking.
 *
 * Arithmetic follows the TFLite / TFLite-Micro int8 reference kernels
 * (asymmetric activations, symmetric per-channel weights, double-rounding
 * fixed-point requantization), so results are bit-exact with the Python
 * reference in hilbench/ml/reference.py and with TFLite for supported ops.
 *
 * Pure C99, no heap, no floating point: runs on ESP8266 (no FPU) as well as
 * Cortex-M, RISC-V and the host simulator.
 */
#ifndef MICROINFER_H
#define MICROINFER_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ESP8266 keeps plain `const` data in scarce DRAM; large tables must live in
 * flash (PROGMEM) and can only be read with aligned 32-bit loads. */
#if defined(ARDUINO_ARCH_ESP8266) || defined(ESP8266)
#include <pgmspace.h>
#define MI_CONST PROGMEM
#define MI_RD_I8(p) ((int8_t)pgm_read_byte((const void *)(p)))
#define MI_RD_I32(p) ((int32_t)pgm_read_dword((const void *)(p)))
#define MI_MEMCPY_CONST(dst, src, n) memcpy_P((dst), (src), (n))
#else
#define MI_CONST
#define MI_RD_I8(p) (*(const int8_t *)(p))
#define MI_RD_I32(p) (*(const int32_t *)(p))
#define MI_MEMCPY_CONST(dst, src, n) memcpy((dst), (src), (n))
#endif

#define MI_VERSION "1.0.0"

typedef enum {
    MI_OP_DENSE = 1,
    MI_OP_CONV2D = 2,
    MI_OP_DWCONV2D = 3,
    MI_OP_MAXPOOL2D = 4,
    MI_OP_AVGPOOL2D = 5,
    MI_OP_RESHAPE = 6
} mi_op_t;

/* mi_layer_t.flags */
#define MI_FLAG_SINGLE_ROUNDING 0x01u /* TFLITE_SINGLE_ROUNDING requantization */

typedef enum {
    MI_OK = 0,
    MI_ERR_ARENA = -1,
    MI_ERR_OP = -2,
    MI_ERR_SHAPE = -3
} mi_status_t;

/* One layer. Tensors are HWC (batch 1). Dense layers use in_c/out_c as the
 * vector lengths with h = w = 1.
 *
 * Weight layouts (identical to TFLite):
 *   DENSE     [out_c][in_c]
 *   CONV2D    [out_c][k_h][k_w][in_c]
 *   DWCONV2D  [k_h][k_w][out_c]          (out_c = in_c * depth_multiplier)
 */
typedef struct {
    uint8_t op;
    uint8_t k_h, k_w;
    uint8_t stride_h, stride_w;
    uint8_t pad_t, pad_l;
    uint8_t flags; /* MI_FLAG_* */
    uint16_t in_h, in_w, in_c;
    uint16_t out_h, out_w, out_c;
    int16_t in_zp, out_zp;
    int16_t act_min, act_max;
    uint16_t n_mult; /* 1 = per-tensor, out_c = per-channel */
    const int8_t *weights;
    const int32_t *bias; /* may be NULL */
    const int32_t *mult;
    const int8_t *shift;
} mi_layer_t;

typedef struct {
    const char *name;
    const char *desc;
    uint16_t n_layers;
    const mi_layer_t *layers;
    uint32_t in_size;
    uint32_t out_size;
    uint32_t arena_size;  /* bytes needed by mi_invoke */
    uint32_t param_bytes; /* weights + bias + multipliers + shifts */
    uint32_t macs;        /* multiply-accumulates per inference */
    uint32_t crc32;       /* crc of all parameters, see mi_model_crc32 */
    uint16_t n_tests;     /* embedded golden vectors */
    const int8_t *test_in;  /* n_tests * in_size */
    const int8_t *test_out; /* n_tests * out_size */
} mi_model_t;

/* Run one inference. `input`/`output` are in RAM. The arena must hold at
 * least model->arena_size bytes. */
int mi_invoke(const mi_model_t *model, const int8_t *input, int8_t *output,
              int8_t *arena, size_t arena_size);

/* CRC-32 (IEEE) over all model parameters, read through MI_RD_* so it also
 * proves that the weights in flash are intact. */
uint32_t mi_model_crc32(const mi_model_t *model);

uint32_t mi_crc32_update(uint32_t crc, const uint8_t *data, size_t len);

/* Exposed for unit tests. */
int32_t mi_multiply_by_quantized_multiplier(int32_t x, int32_t mult, int shift);
int32_t mi_multiply_by_quantized_multiplier_single(int32_t x, int32_t mult, int shift);

#ifdef __cplusplus
}
#endif

#endif /* MICROINFER_H */
