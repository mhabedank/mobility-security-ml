idf_component_register(SRCS "msml_can_features.c" "msml_alarm.c"
                       INCLUDE_DIRS "include")
# Keep float results identical to the host build (no fused multiply-add contraction).
target_compile_options(${COMPONENT_LIB} PRIVATE -O2 -ffp-contract=off)
