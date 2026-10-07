/*
 * HIL bench application - see benchapp.h and docs/protocol.md.
 *
 * No printf/float/heap: only small fixed buffers so the same code runs on an
 * ESP8266 with ~40 KiB free RAM.
 */
#include "benchapp.h"

#include <string.h>

#include "hal.h"
#include "microinfer.h"
#include "model_zoo.h"

#ifndef BENCH_LINE_MAX
#define BENCH_LINE_MAX (2u * MI_ZOO_MAX_IN + 96u)
#endif
#define BENCH_MAX_ARGS 4

/* 4-byte aligned scratch memory. */
static uint32_t s_arena_words[(MI_ZOO_ARENA_SIZE + 3u) / 4u];
static int8_t *const s_arena = (int8_t *)s_arena_words;
static int8_t s_in[MI_ZOO_MAX_IN];
static int8_t s_out[MI_ZOO_MAX_OUT];
static int8_t s_ref[MI_ZOO_MAX_OUT];

static char s_line[BENCH_LINE_MAX];
static uint32_t s_line_len;
static uint8_t s_overflow;
static uint32_t s_req_id;
static uint32_t s_inferences;

/* ---- output helpers ----------------------------------------------------- */

static void out_raw(const char *s)
{
    hal_write(s, strlen(s));
}

static void out_u32(uint32_t v)
{
    char buf[11];
    int i = 10;
    buf[i] = '\0';
    do {
        buf[--i] = (char)('0' + v % 10u);
        v /= 10u;
    } while (v);
    out_raw(&buf[i]);
}

static void out_i32(int32_t v)
{
    if (v < 0) {
        out_raw("-");
        out_u32((uint32_t)(-(v + 1)) + 1u);
    } else {
        out_u32((uint32_t)v);
    }
}

static const char k_hex[] = "0123456789abcdef";

static void out_hex_bytes(const uint8_t *p, uint32_t n)
{
    char buf[32];
    uint32_t k = 0;
    for (uint32_t i = 0; i < n; i++) {
        buf[k++] = k_hex[p[i] >> 4];
        buf[k++] = k_hex[p[i] & 15u];
        if (k == sizeof(buf)) {
            hal_write(buf, k);
            k = 0;
        }
    }
    if (k) hal_write(buf, k);
}

static void out_hex32(uint32_t v)
{
    uint8_t b[4] = {(uint8_t)(v >> 24), (uint8_t)(v >> 16), (uint8_t)(v >> 8), (uint8_t)v};
    out_hex_bytes(b, 4);
}

static void out_jstr(const char *s)
{
    out_raw("\"");
    for (; *s; s++) {
        char c = *s;
        if (c == '"' || c == '\\') {
            char esc[2] = {'\\', c};
            hal_write(esc, 2);
        } else if ((unsigned char)c < 0x20) {
            out_raw(" ");
        } else {
            hal_write(&c, 1);
        }
    }
    out_raw("\"");
}

/* ,"key": */
static void key(const char *k)
{
    out_raw(",\"");
    out_raw(k);
    out_raw("\":");
}

static void kv_u32(const char *k, uint32_t v) { key(k); out_u32(v); }
static void kv_i32(const char *k, int32_t v) { key(k); out_i32(v); }
static void kv_str(const char *k, const char *v) { key(k); out_jstr(v); }
static void kv_bool(const char *k, int v) { key(k); out_raw(v ? "true" : "false"); }
static void kv_hex32(const char *k, uint32_t v) { key(k); out_raw("\""); out_hex32(v); out_raw("\""); }

static void resp_begin(int ok)
{
    out_raw("@{\"id\":");
    out_u32(s_req_id);
    out_raw(ok ? ",\"ok\":true" : ",\"ok\":false");
}

static void resp_end(void)
{
    out_raw("}\n");
}

static void resp_error(const char *err)
{
    resp_begin(0);
    kv_str("err", err);
    resp_end();
}

/* ---- parsing helpers ---------------------------------------------------- */

static int parse_u32(const char *s, uint32_t *out)
{
    uint32_t v = 0;
    if (!s || !*s) return 0;
    for (; *s; s++) {
        if (*s < '0' || *s > '9') return 0;
        v = v * 10u + (uint32_t)(*s - '0');
    }
    *out = v;
    return 1;
}

static int hexval(char c)
{
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}

/* Returns decoded length or -1. */
static int32_t decode_hex(const char *s, uint8_t *dst, uint32_t cap)
{
    uint32_t n = (uint32_t)strlen(s);
    if (n % 2u || n / 2u > cap) return -1;
    for (uint32_t i = 0; i < n / 2u; i++) {
        int hi = hexval(s[2 * i]);
        int lo = hexval(s[2 * i + 1]);
        if (hi < 0 || lo < 0) return -1;
        dst[i] = (uint8_t)((hi << 4) | lo);
    }
    return (int32_t)(n / 2u);
}

static const mi_model_t *find_model(const char *arg)
{
    uint32_t idx;
    if (!arg) return NULL;
    if (parse_u32(arg, &idx)) {
        return idx < mi_zoo_count ? mi_zoo[idx] : NULL;
    }
    for (unsigned i = 0; i < mi_zoo_count; i++) {
        if (strcmp(mi_zoo[i]->name, arg) == 0) return mi_zoo[i];
    }
    return NULL;
}

static int run_model(const mi_model_t *m, const int8_t *in, int8_t *out, uint32_t *us, uint32_t *cyc)
{
    const uint32_t c0 = hal_cycles();
    const uint32_t t0 = hal_micros();
    int rc = mi_invoke(m, in, out, s_arena, sizeof(s_arena_words));
    const uint32_t t1 = hal_micros();
    const uint32_t c1 = hal_cycles();
    *us = t1 - t0;
    *cyc = c1 - c0;
    s_inferences++;
    return rc;
}

/* ---- commands ----------------------------------------------------------- */

static void cmd_ping(void)
{
    resp_begin(1);
    kv_bool("pong", 1);
    kv_u32("uptime_ms", hal_millis());
    resp_end();
}

static void cmd_info(void)
{
    resp_begin(1);
    kv_str("fw", HIL_FW_VERSION);
    kv_u32("proto", HIL_PROTOCOL_VERSION);
    kv_hex32("build", (uint32_t)(HIL_BUILD_ID));
    kv_str("target", hal_target());
    kv_str("chip", hal_chip());
    kv_str("uid", hal_uid());
    kv_str("framework", hal_framework());
    kv_str("engine", "microinfer " MI_VERSION);
    kv_u32("cpu_mhz", hal_cpu_mhz());
    kv_bool("has_cycles", hal_cycles() != 0u || hal_cycles() != 0u);
    kv_u32("free_heap", hal_free_heap());
    kv_u32("min_free_heap", hal_min_free_heap());
    kv_u32("arena", (uint32_t)sizeof(s_arena_words));
    kv_u32("line_max", BENCH_LINE_MAX);
    kv_u32("models", mi_zoo_count);
    kv_str("reset_reason", hal_reset_reason());
    kv_u32("uptime_ms", hal_millis());
    kv_u32("inferences", s_inferences);
    resp_end();
}

static void cmd_models(void)
{
    resp_begin(1);
    key("models");
    out_raw("[");
    for (unsigned i = 0; i < mi_zoo_count; i++) {
        const mi_model_t *m = mi_zoo[i];
        out_raw(i ? ",{\"idx\":" : "{\"idx\":");
        out_u32(i);
        kv_str("name", m->name);
        kv_u32("in", m->in_size);
        kv_u32("out", m->out_size);
        kv_u32("layers", m->n_layers);
        kv_u32("arena", m->arena_size);
        kv_u32("params", m->param_bytes);
        kv_u32("macs", m->macs);
        kv_hex32("crc", m->crc32);
        kv_u32("tests", m->n_tests);
        out_raw("}");
    }
    out_raw("]");
    resp_end();
}

static void cmd_infer(int argc, char **argv)
{
    const mi_model_t *m = find_model(argc > 1 ? argv[1] : NULL);
    if (!m) { resp_error("unknown model"); return; }
    if (argc < 3) { resp_error("missing input"); return; }
    int32_t n = decode_hex(argv[2], (uint8_t *)s_in, sizeof(s_in));
    if (n < 0) { resp_error("bad hex"); return; }
    if ((uint32_t)n != m->in_size) { resp_error("input size mismatch"); return; }
    uint32_t us, cyc;
    int rc = run_model(m, s_in, s_out, &us, &cyc);
    if (rc != MI_OK) { resp_error("invoke failed"); return; }
    resp_begin(1);
    kv_str("model", m->name);
    key("out");
    out_raw("\"");
    out_hex_bytes((const uint8_t *)s_out, m->out_size);
    out_raw("\"");
    kv_u32("us", us);
    kv_u32("cycles", cyc);
    kv_hex32("in_crc", mi_crc32_update(0, (const uint8_t *)s_in, m->in_size));
    resp_end();
}

static void cmd_bench(int argc, char **argv)
{
    const mi_model_t *m = find_model(argc > 1 ? argv[1] : NULL);
    uint32_t n = 10, warmup = 1;
    if (!m) { resp_error("unknown model"); return; }
    if (argc > 2 && !parse_u32(argv[2], &n)) { resp_error("bad count"); return; }
    if (argc > 3 && !parse_u32(argv[3], &warmup)) { resp_error("bad warmup"); return; }
    if (n == 0 || n > 100000u) { resp_error("count out of range"); return; }
    if (m->n_tests) {
        MI_MEMCPY_CONST(s_in, m->test_in, m->in_size);
    } else {
        memset(s_in, 0, m->in_size);
    }
    const uint32_t heap_before = hal_free_heap();
    uint32_t us, cyc;
    for (uint32_t i = 0; i < warmup; i++) {
        if (run_model(m, s_in, s_ref, &us, &cyc) != MI_OK) { resp_error("invoke failed"); return; }
        hal_yield();
    }
    if (warmup == 0 && run_model(m, s_in, s_ref, &us, &cyc) != MI_OK) { resp_error("invoke failed"); return; }
    uint32_t us_min = 0xFFFFFFFFu, us_max = 0, us_total = 0;
    uint32_t cyc_min = 0xFFFFFFFFu, cyc_max = 0;
    uint32_t cyc_total_hi = 0, cyc_total_lo = 0; /* 64-bit sum without 64-bit printing */
    uint8_t stable = 1;
    for (uint32_t i = 0; i < n; i++) {
        if (run_model(m, s_in, s_out, &us, &cyc) != MI_OK) { resp_error("invoke failed"); return; }
        if (memcmp(s_out, s_ref, m->out_size) != 0) stable = 0;
        if (us < us_min) us_min = us;
        if (us > us_max) us_max = us;
        if (cyc < cyc_min) cyc_min = cyc;
        if (cyc > cyc_max) cyc_max = cyc;
        us_total += us;
        uint32_t lo = cyc_total_lo + cyc;
        if (lo < cyc_total_lo) cyc_total_hi++;
        cyc_total_lo = lo;
        hal_yield();
    }
    /* average cycles = (hi:lo) / n, done in 32-bit pieces */
    uint32_t cyc_avg;
    if (cyc_total_hi == 0) {
        cyc_avg = cyc_total_lo / n;
    } else {
        cyc_avg = (uint32_t)((((uint64_t)cyc_total_hi << 32) | cyc_total_lo) / n);
    }
    resp_begin(1);
    kv_str("model", m->name);
    kv_u32("n", n);
    kv_u32("us_min", us_min);
    kv_u32("us_max", us_max);
    kv_u32("us_avg", us_total / n);
    kv_u32("us_total", us_total);
    kv_u32("cyc_min", cyc_min);
    kv_u32("cyc_max", cyc_max);
    kv_u32("cyc_avg", cyc_avg);
    kv_u32("macs", m->macs);
    kv_bool("stable", stable);
    kv_u32("heap_before", heap_before);
    kv_u32("heap_after", hal_free_heap());
    kv_u32("min_free_heap", hal_min_free_heap());
    resp_end();
}

static void cmd_selftest(int argc, char **argv)
{
    const mi_model_t *m = find_model(argc > 1 ? argv[1] : NULL);
    if (!m) { resp_error("unknown model"); return; }
    uint32_t passed = 0;
    int32_t first_fail = -1;
    uint32_t us_total = 0;
    for (uint16_t t = 0; t < m->n_tests; t++) {
        uint32_t us, cyc;
        MI_MEMCPY_CONST(s_in, m->test_in + (uint32_t)t * m->in_size, m->in_size);
        MI_MEMCPY_CONST(s_ref, m->test_out + (uint32_t)t * m->out_size, m->out_size);
        if (run_model(m, s_in, s_out, &us, &cyc) == MI_OK && memcmp(s_out, s_ref, m->out_size) == 0) {
            passed++;
        } else if (first_fail < 0) {
            first_fail = t;
        }
        us_total += us;
        hal_yield();
    }
    const uint32_t crc = mi_model_crc32(m);
    resp_begin(1);
    kv_str("model", m->name);
    kv_u32("passed", passed);
    kv_u32("total", m->n_tests);
    kv_i32("first_fail", first_fail);
    kv_bool("crc_ok", crc == m->crc32);
    kv_u32("us_total", us_total);
    resp_end();
}

static void cmd_verify(int argc, char **argv)
{
    const mi_model_t *m = find_model(argc > 1 ? argv[1] : NULL);
    if (!m) { resp_error("unknown model"); return; }
    const uint32_t t0 = hal_micros();
    const uint32_t crc = mi_model_crc32(m);
    const uint32_t us = hal_micros() - t0;
    resp_begin(1);
    kv_str("model", m->name);
    kv_hex32("crc", crc);
    kv_hex32("expected", m->crc32);
    kv_bool("match", crc == m->crc32);
    kv_u32("us", us);
    resp_end();
}

static void cmd_mem(void)
{
    resp_begin(1);
    kv_u32("free_heap", hal_free_heap());
    kv_u32("min_free_heap", hal_min_free_heap());
    kv_u32("arena", (uint32_t)sizeof(s_arena_words));
    kv_u32("static_bufs", (uint32_t)(sizeof(s_arena_words) + sizeof(s_in) + sizeof(s_out) +
                                     sizeof(s_ref) + sizeof(s_line)));
    resp_end();
}

static void cmd_echo(int argc, char **argv)
{
    if (argc < 2) { resp_error("missing data"); return; }
    int32_t n = decode_hex(argv[1], (uint8_t *)s_in, sizeof(s_in));
    if (n < 0) { resp_error("bad hex"); return; }
    resp_begin(1);
    kv_u32("len", (uint32_t)n);
    key("data");
    out_raw("\"");
    out_hex_bytes((const uint8_t *)s_in, (uint32_t)n);
    out_raw("\"");
    kv_hex32("crc", mi_crc32_update(0, (const uint8_t *)s_in, (uint32_t)n));
    resp_end();
}

static void cmd_reset(void)
{
    resp_begin(1);
    kv_bool("resetting", 1);
    resp_end();
    const uint32_t t0 = hal_millis();
    while (hal_millis() - t0 < 50u) {
        hal_yield(); /* let the UART drain */
    }
    hal_reset();
}

static void execute(char *line)
{
    char *argv[BENCH_MAX_ARGS];
    int argc = 0;
    s_req_id = 0;

    char *p = line;
    while (*p == ' ') p++;
    if (*p == '#') {
        p++;
        uint32_t id = 0;
        while (*p >= '0' && *p <= '9') id = id * 10u + (uint32_t)(*p++ - '0');
        s_req_id = id;
    }
    while (*p && argc < BENCH_MAX_ARGS) {
        while (*p == ' ') *p++ = '\0';
        if (!*p) break;
        argv[argc++] = p;
        while (*p && *p != ' ') p++;
    }
    while (*p == ' ') *p++ = '\0';
    if (argc == 0) return;
    const char *cmd = argv[0];

    if (strcmp(cmd, "PING") == 0) cmd_ping();
    else if (strcmp(cmd, "INFO") == 0) cmd_info();
    else if (strcmp(cmd, "MODELS") == 0) cmd_models();
    else if (strcmp(cmd, "INFER") == 0) cmd_infer(argc, argv);
    else if (strcmp(cmd, "BENCH") == 0) cmd_bench(argc, argv);
    else if (strcmp(cmd, "SELFTEST") == 0) cmd_selftest(argc, argv);
    else if (strcmp(cmd, "VERIFY") == 0) cmd_verify(argc, argv);
    else if (strcmp(cmd, "MEM") == 0) cmd_mem();
    else if (strcmp(cmd, "ECHO") == 0) cmd_echo(argc, argv);
    else if (strcmp(cmd, "RESET") == 0) cmd_reset();
    else resp_error("unknown command");
}

void bench_feed(int c)
{
    if (c == '\r') return;
    if (c == '\n') {
        if (s_overflow) {
            s_req_id = 0;
            resp_error("line too long");
        } else {
            s_line[s_line_len] = '\0';
            execute(s_line);
        }
        s_line_len = 0;
        s_overflow = 0;
        return;
    }
    if (s_line_len + 1u < sizeof(s_line)) {
        s_line[s_line_len++] = (char)c;
    } else {
        s_overflow = 1;
    }
}

void bench_poll(void)
{
    int c;
    while ((c = hal_read()) >= 0) {
        bench_feed(c);
    }
}

void bench_init(void)
{
    s_line_len = 0;
    s_overflow = 0;
    out_raw("\n@{\"evt\":\"boot\"");
    kv_str("fw", HIL_FW_VERSION);
    kv_hex32("build", (uint32_t)(HIL_BUILD_ID));
    kv_str("target", hal_target());
    kv_str("reset_reason", hal_reset_reason());
    kv_u32("models", mi_zoo_count);
    out_raw("}\n");
}
