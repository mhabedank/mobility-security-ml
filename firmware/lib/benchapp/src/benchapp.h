/*
 * HIL bench application: line based request/response protocol on the serial
 * port. See docs/protocol.md.
 *
 *   host -> device:  "#<id> <COMMAND> [args...]\n"
 *   device -> host:  "@{json}\n"   (everything else is log output)
 */
#ifndef HIL_BENCHAPP_H
#define HIL_BENCHAPP_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define HIL_FW_VERSION "0.1.0"
#define HIL_PROTOCOL_VERSION 1

/* Injected by the build (hilbench build) to prove which image is running. */
#ifndef HIL_BUILD_ID
#define HIL_BUILD_ID 0u
#endif

void bench_init(void); /* emit boot event */
void bench_poll(void); /* drain hal_read() and execute complete lines */
void bench_feed(int c); /* feed a single received byte */

#ifdef __cplusplus
}
#endif

#endif /* HIL_BENCHAPP_H */
