# ESP-IDF benchmark app for can-ids-tiny. Works for any target with an FPU-less or FPU core:
#   idf.py set-target esp32s3   (or esp32, esp32c3, ...)
#   idf.py build flash monitor
cmake_minimum_required(VERSION 3.16)
set(EXTRA_COMPONENT_DIRS "${CMAKE_CURRENT_LIST_DIR}/../../../firmware/components")
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(can_ids_tiny_bench)
