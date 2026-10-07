/*
 * Host simulator HAL: the bench firmware as a Linux/macOS process talking
 * over stdin/stdout. Used for CI and for developing tests without hardware.
 *
 * Environment variables (fault injection for harness tests):
 *   HIL_SIM_BOOT_NOISE=1          print bootloader-like garbage before the boot event
 *   HIL_SIM_SLOWDOWN=N            busy-wait N microseconds per hal_yield()
 *   HIL_SIM_CRASH_AFTER_LINES=N   "watchdog reset" when the N-th command arrives
 *   HIL_SIM_HANG_AFTER_LINES=N    stop responding at the N-th command
 */
#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#include "hal.h"

static char **s_argv;
static const char *s_reset_reason = "power_on";

void hal_native_init(int argc, char **argv)
{
    (void)argc;
    s_argv = argv;
    const char *rr = getenv("HIL_SIM_RESET_REASON");
    if (rr && *rr) s_reset_reason = rr;
    const char *noise = getenv("HIL_SIM_BOOT_NOISE");
    if (noise && *noise == '1') {
        static const char junk[] = "\x00\xff ets Jan  8 2013,rst cause:2, boot mode:(3,6)\r\n\xfe\x8a load 0x4010f000\r\n";
        hal_write(junk, sizeof(junk) - 1);
    }
}

void hal_write(const char *data, size_t len)
{
    while (len) {
        ssize_t n = write(STDOUT_FILENO, data, len);
        if (n < 0) {
            if (errno == EINTR) continue;
            exit(0); /* host went away */
        }
        data += n;
        len -= (size_t)n;
    }
}

int hal_read(void)
{
    unsigned char c;
    ssize_t n;
    do {
        n = read(STDIN_FILENO, &c, 1); /* blocking: the simulator idles here */
    } while (n < 0 && errno == EINTR);
    if (n <= 0) exit(0);
    return c;
}

static uint64_t now_us(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000u + (uint64_t)ts.tv_nsec / 1000u;
}

static uint64_t s_t0;

uint32_t hal_micros(void)
{
    if (!s_t0) s_t0 = now_us();
    return (uint32_t)(now_us() - s_t0);
}

uint32_t hal_millis(void) { return hal_micros() / 1000u; }
uint32_t hal_cycles(void) { return 0; }
uint32_t hal_cpu_mhz(void) { return 0; }
uint32_t hal_free_heap(void) { return 0; }
uint32_t hal_min_free_heap(void) { return 0; }
const char *hal_target(void) { return "native"; }
const char *hal_chip(void) { return "host-sim"; }
const char *hal_uid(void)
{
    const char *uid = getenv("HIL_SIM_UID");
    return uid ? uid : "sim-0";
}
const char *hal_framework(void) { return "native-posix"; }
const char *hal_reset_reason(void) { return s_reset_reason; }

void hal_yield(void)
{
    const char *slow = getenv("HIL_SIM_SLOWDOWN");
    if (slow) {
        uint64_t until = now_us() + (uint64_t)strtoul(slow, NULL, 10);
        while (now_us() < until) {
        }
    }
}

static void reboot(const char *reason)
{
    setenv("HIL_SIM_RESET_REASON", reason, 1);
    unsetenv("HIL_SIM_BOOT_NOISE");
    unsetenv("HIL_SIM_CRASH_AFTER_LINES");
    unsetenv("HIL_SIM_HANG_AFTER_LINES");
    fflush(NULL);
    execv("/proc/self/exe", s_argv);
    execvp(s_argv[0], s_argv); /* non-Linux fallback */
    exit(3);
}

void hal_reset(void)
{
    /* Emulate a reboot by re-executing ourselves on the same pipes. */
    reboot("software");
}

void hal_native_crash(void)
{
    static const char dump[] = "\r\nSoft WDT reset\r\n\r\n>>>stack>>>\r\nctx: cont\r\n"
                               "sp: 3ffffdc0 end: 3fffffc0 offset: 01a0\r\n<<<stack<<<\r\n";
    hal_write(dump, sizeof(dump) - 1);
    reboot("watchdog");
}

void hal_native_hang(void)
{
    for (;;) {
        if (hal_read() < 0) exit(0); /* swallow input forever */
    }
}
