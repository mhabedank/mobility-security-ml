# Host simulator build (no PlatformIO needed).
#   make -C firmware/native            -> build/hilbench-sim
#   make -C firmware/native CFLAGS="-O2 -DMI_EXCLUDE_HAR_CNN1D"  -> without a model
CC ?= cc
HIL_BUILD_ID ?= 0
OUT ?= build
CFLAGS ?= -O2
override CFLAGS += -std=c99 -Wall -Wextra -Werror -Wshadow -Wconversion -Wno-sign-conversion \
          -I../lib/microinfer/src -I../lib/benchapp/src -I../lib/modelzoo/src \
          -DHIL_BUILD_ID=$(HIL_BUILD_ID)

LIB_SRCS = ../lib/microinfer/src/microinfer.c ../lib/benchapp/src/benchapp.c ../lib/modelzoo/src/model_zoo.c
SRCS = $(LIB_SRCS) hal_native.c main.c

$(OUT)/hilbench-sim: $(SRCS) $(wildcard ../lib/*/src/*.h) Makefile
	@mkdir -p $(OUT)
	$(CC) $(CFLAGS) -o $@ $(SRCS)

clean:
	rm -rf $(OUT)

.PHONY: clean
