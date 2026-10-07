/*
 * Host harness: reads frames from a binary file and writes one float score per frame.
 * Record layout (little endian, packed): int64 ts_us, uint16 can_id, uint8 dlc, uint8 data[8].
 * Used by the parity test that compares C scores with the Python pipeline.
 */
#include <stdio.h>
#include <stdlib.h>

#include "can_ids_tiny.h"

int main(int argc, char **argv)
{
    if (argc != 3) {
        fprintf(stderr, "usage: %s frames.bin scores.bin\n", argv[0]);
        return 2;
    }
    FILE *in = fopen(argv[1], "rb");
    FILE *out = fopen(argv[2], "wb");
    if (in == NULL || out == NULL) {
        perror("fopen");
        return 1;
    }
    static can_ids_tiny_t ids;
    can_ids_tiny_init(&ids);
    unsigned char rec[19];
    while (fread(rec, 1, sizeof(rec), in) == sizeof(rec)) {
        int64_t ts = 0;
        for (int i = 7; i >= 0; i--) {
            ts = (ts << 8) | rec[i];
        }
        uint16_t id = (uint16_t)(rec[8] | (rec[9] << 8));
        float s = can_ids_tiny_score(&ids, ts, id, rec[10], &rec[11]);
        fwrite(&s, sizeof(s), 1, out);
    }
    fclose(in);
    fclose(out);
    return 0;
}
