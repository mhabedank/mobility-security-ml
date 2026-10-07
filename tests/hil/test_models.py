"""The models compiled into the firmware are exactly the host's reference models."""
from hilbench.ml.zoo import load_zoo


def test_model_catalogue_matches_host(dut):
    zoo = load_zoo()
    device_models = dut.models()
    expected = {n for n in zoo if n not in dut.target.excluded_models}
    assert set(device_models) == expected
    for name, m in device_models.items():
        ref = zoo[name]
        assert m["crc"] == f"{ref.crc32():08x}", f"{name}: firmware built from a different model"
        assert m["in"] == ref.in_size and m["out"] == ref.out_size
        assert m["macs"] == ref.macs()
        assert m["arena"] == ref.arena_size()
        assert m["arena"] <= dut.info["arena"]


def test_weights_intact_in_flash(dut, model_name):
    dut.require_model(model_name)
    r = dut.device.verify(model_name)
    assert r["match"], f"CRC of weights read back from flash: {r['crc']} != {r['expected']}"


def test_embedded_golden_vectors(dut, model_name):
    dut.require_model(model_name)
    r = dut.device.selftest(model_name)
    assert r["crc_ok"]
    assert r["passed"] == r["total"], f"golden vector #{r['first_fail']} differs"
