# PlatformIO post-script: write $BUILD_DIR/hil_manifest.json describing how to
# flash the build without PlatformIO (used by hilbench's esptool flasher).
import json
import os

Import("env")  # noqa: F821  (provided by SCons)


def _write_manifest(source, target, env):
    board = env.BoardConfig()
    build_dir = env.subst("$BUILD_DIR")
    app = os.path.join(build_dir, env.subst("${PROGNAME}.bin"))
    platform = env.get("PIOPLATFORM", "")
    manifest = {
        "pio_env": env.subst("$PIOENV"),
        "platform": platform,
        "board": board.id,
        "mcu": board.get("build.mcu", ""),
        "build_id": "0x%08x" % (int(os.environ.get("HIL_BUILD_ID", "0"), 0) & 0xFFFFFFFF),
        "flash_images": [],
    }
    if platform == "espressif32":
        for offset, image in env.get("FLASH_EXTRA_IMAGES", []):
            manifest["flash_images"].append({"offset": env.subst(offset), "path": env.subst(image)})
        manifest["flash_images"].append({"offset": env.subst("$ESP32_APP_OFFSET"), "path": app})
        try:
            manifest["flash_mode"] = env.subst("${__get_board_flash_mode(__env__)}")
            manifest["flash_freq"] = env.subst("${__get_board_f_image(__env__)}")
        except Exception:  # older/newer platform versions
            manifest["flash_mode"] = board.get("build.flash_mode", "dio")
    elif platform == "espressif8266":
        manifest["flash_images"].append({"offset": "0x0", "path": app})
    with open(os.path.join(build_dir, "hil_manifest.json"), "w") as fh:
        json.dump(manifest, fh, indent=2)


env.AddPostAction("buildprog", _write_manifest)  # noqa: F821
