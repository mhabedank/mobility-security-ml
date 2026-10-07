# PlatformIO pre-script: inject HIL_BUILD_ID so the host can verify which
# image is actually running on a board after flashing.
import os

Import("env")  # noqa: F821  (provided by SCons)

build_id = os.environ.get("HIL_BUILD_ID", "0")
try:
    value = int(build_id, 0) & 0xFFFFFFFF
except ValueError:
    value = 0
env.Append(CPPDEFINES=[("HIL_BUILD_ID", "0x%08xu" % value)])  # noqa: F821
