import pytest

from hilbench import flash
from hilbench.config import load_lab
from hilbench.flash import Firmware, FlashError, make_flasher
from hilbench.power import CommandPower, NoPower, PowerError, make_power


def _fw(tmp_path):
    return Firmware("esp32", tmp_path, {
        "build_id": "0x1", "files": {"bin": "firmware.bin", "elf": "firmware.elf"}, "flash_mode": "dio",
        "flash_images": [{"offset": "0x1000", "file": "bootloader.bin"},
                         {"offset": "0x10000", "file": "firmware.bin"}]})


def _board(lab, target, **kw):
    from dataclasses import replace
    return replace(lab.boards[0], id="x", target=lab.targets[target], port="/dev/ttyUSB9", **kw)


@pytest.mark.parametrize("major,write,before", [(4, "write_flash", "default_reset"),
                                                (5, "write-flash", "default-reset")])
def test_esptool_command(tmp_path, monkeypatch, major, write, before):
    monkeypatch.setattr(flash, "_esptool_major", lambda: major)
    lab = load_lab()
    cmd = make_flasher(_board(lab, "esp32"), lab).command("/dev/ttyUSB9", _fw(tmp_path))
    assert cmd[1:3] == ["-m", "esptool"]
    assert write in cmd and before in cmd
    assert cmd[cmd.index("--chip") + 1] == "esp32"
    assert cmd[-4:] == ["0x1000", str(tmp_path / "bootloader.bin"), "0x10000", str(tmp_path / "firmware.bin")]


def test_command_flasher_template(tmp_path):
    lab = load_lab()
    b = _board(lab, "stm32f446", flasher="command",
               flasher_options={"command": "st-flash --reset write {bin} 0x08000000"})
    cmd = make_flasher(b, lab).command("/dev/ttyACM0", _fw(tmp_path))
    assert cmd == ["st-flash", "--reset", "write", str(tmp_path / "firmware.bin"), "0x08000000"]


def test_platformio_flasher(tmp_path):
    lab = load_lab()
    cmd = make_flasher(_board(lab, "rp2040"), lab).command("/dev/ttyACM0", _fw(tmp_path))
    assert cmd[-6:] == ["-t", "nobuild", "-t", "upload", "--upload-port", "/dev/ttyACM0"]


def test_unknown_flasher(tmp_path):
    lab = load_lab()
    with pytest.raises(FlashError):
        make_flasher(_board(lab, "esp32", flasher="magic"), lab)


def test_power(tmp_path):
    assert isinstance(make_power(None), NoPower)
    with pytest.raises(PowerError):
        make_power({}).cycle()
    marker = tmp_path / "state"
    p = make_power({"type": "command", "on": f"touch {marker}", "off": f"rm -f {marker}", "off_s": 0, "settle_s": 0})
    assert isinstance(p, CommandPower)
    p.cycle()
    assert marker.exists()
    p.off()
    assert not marker.exists()
    with pytest.raises(PowerError):
        make_power({"type": "command", "on": "false", "off": "true"}).on()
