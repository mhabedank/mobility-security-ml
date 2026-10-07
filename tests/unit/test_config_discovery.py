import pytest

from hilbench.config import ConfigError, load_lab, load_targets
from hilbench.discovery import DiscoveryError, PortInfo, _matches, match_probe, parse_esptool_chip, resolve_port


def test_default_catalogue_loads():
    t = load_targets()
    assert {"native", "esp8266", "esp32", "esp32s3", "esp32c3", "rp2040", "stm32f446", "nrf52840"} <= set(t)
    assert t["esp32s3_usb"].esptool_chip == "esp32s3"  # inherited via extends
    assert t["esp32s3_usb"].reset == "esp_usb_jtag"


def test_every_pio_target_has_an_env():
    ini = (load_lab().firmware_dir / "platformio.ini").read_text()
    for t in load_targets().values():
        if t.build == "platformio":
            assert f"[env:{t.pio_env}]" in ini, t.name


def test_lab_yaml_validation(tmp_path):
    p = tmp_path / "boards.yaml"
    p.write_text("boards:\n  - id: a\n    target: nope\n")
    with pytest.raises(ConfigError, match="unknown target"):
        load_lab(p)
    p.write_text("boards:\n  - id: a\n    target: esp32\n    colour: red\n")
    with pytest.raises(ConfigError, match="unknown keys"):
        load_lab(p)
    p.write_text("boards:\n  - id: a\n    target: esp32\n  - id: a\n    target: esp32\n")
    with pytest.raises(ConfigError, match="duplicate"):
        load_lab(p)


def test_select(tmp_path):
    p = tmp_path / "boards.yaml"
    p.write_text("boards:\n"
                 "  - {id: a, target: esp32, tags: [x]}\n"
                 "  - {id: b, target: esp8266}\n"
                 "  - {id: c, target: esp8266, enabled: false}\n")
    lab = load_lab(p)
    assert [b.id for b in lab.select()] == ["a", "b"]
    assert [b.id for b in lab.select(targets=["esp8266"])] == ["b"]
    assert [b.id for b in lab.select(tags=["x"])] == ["a"]
    assert [b.id for b in lab.select(board_ids=["c"])] == ["c"]  # explicit selection wins
    with pytest.raises(ConfigError):
        lab.select(board_ids=["zzz"])


PORTS = [
    PortInfo("/dev/ttyUSB0", 0x1A86, 0x7523, None, "1-1.2:1.0", "USB Serial"),
    PortInfo("/dev/ttyUSB1", 0x1A86, 0x7523, None, "1-1.3:1.0", "USB Serial"),
    PortInfo("/dev/ttyUSB2", 0x10C4, 0xEA60, "0001", "1-1.4:1.0", "CP2102 USB to UART"),
]


def test_port_matching(tmp_path):
    assert _matches(PORTS[0], {"location": "1-1.2"})
    assert _matches(PORTS[2], {"vid_pid": "10c4:ea60", "serial_number": "0001"})
    assert not _matches(PORTS[2], {"serial_number": "0002"})
    p = tmp_path / "boards.yaml"
    p.write_text("boards:\n"
                 "  - {id: one, target: esp8266, match: {location: '1-1.3'}}\n"
                 "  - {id: amb, target: esp8266, match: {vid_pid: '1a86:7523'}}\n"
                 "  - {id: gone, target: esp32, match: {serial_number: 'X'}}\n"
                 "  - {id: fixed, target: esp32, port: 'rfc2217://pi:4000'}\n")
    lab = load_lab(p)
    assert resolve_port(lab.board("one"), PORTS) == "/dev/ttyUSB1"
    assert resolve_port(lab.board("fixed"), PORTS) == "rfc2217://pi:4000"
    with pytest.raises(DiscoveryError, match="2 ports match"):
        resolve_port(lab.board("amb"), PORTS)
    with pytest.raises(DiscoveryError, match="no connected port"):
        resolve_port(lab.board("gone"), PORTS)


@pytest.mark.parametrize("out,chip,targets", [
    ("Detecting chip type... ESP8266\nChip is ESP8266EX\n", "ESP8266EX", {"esp8266"}),
    ("Chip is ESP32-D0WD-V3 (revision v3.1)\n", "ESP32-D0WD-V3 (revision v3.1)", {"esp32"}),
    ("Chip type:          ESP32-S3 (QFN56) (revision v0.2)\n", "ESP32-S3 (QFN56) (revision v0.2)",
     {"esp32s3", "esp32s3_usb"}),
    ("Chip is ESP32-C3 (QFN32) (revision v0.4)\n", "ESP32-C3 (QFN32) (revision v0.4)",
     {"esp32c3", "esp32c3_usb"}),
])
def test_esptool_chip_detection(out, chip, targets):
    assert parse_esptool_chip(out) == chip
    assert set(match_probe(chip, load_targets())) - {"esp8266_160mhz"} == targets


def test_power_on_off_keys_survive_yaml(tmp_path):
    from hilbench.power import CommandPower, make_power

    p = tmp_path / "boards.yaml"
    p.write_text("boards:\n  - {id: a, target: esp32, power: {type: command, on: 'true', off: 'true'}}\n")
    power = make_power(load_lab(p).board("a").power)
    assert isinstance(power, CommandPower) and power.on_cmd == "true"
