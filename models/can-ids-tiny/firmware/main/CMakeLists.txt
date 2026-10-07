idf_component_register(SRCS "main.c" "../../c/can_ids_tiny.c"
                       INCLUDE_DIRS "." "../../c" "../../c/generated"
                       REQUIRES msml_can_features esp_timer)
target_compile_options(${COMPONENT_LIB} PRIVATE -O2 -ffp-contract=off)
