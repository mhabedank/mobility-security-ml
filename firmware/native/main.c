/* Host simulator entry point: same bench application, stdin/stdout link. */
#include <stdlib.h>

#include "benchapp.h"
#include "hal.h"

void hal_native_init(int argc, char **argv);
void hal_native_crash(void);
void hal_native_hang(void);

int main(int argc, char **argv)
{
    /* Fault injection for testing the host harness (see hal_native.c). */
    const char *crash = getenv("HIL_SIM_CRASH_AFTER_LINES");
    const char *hang = getenv("HIL_SIM_HANG_AFTER_LINES");
    long crash_after = crash ? strtol(crash, NULL, 10) : -1;
    long hang_after = hang ? strtol(hang, NULL, 10) : -1;
    long lines = 0;

    hal_native_init(argc, argv);
    bench_init();
    for (;;) {
        int c = hal_read();
        if (c == '\n') {
            lines++;
            if (lines == crash_after) hal_native_crash();
            if (lines == hang_after) hal_native_hang();
        }
        bench_feed(c);
    }
}
