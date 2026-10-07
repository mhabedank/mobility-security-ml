"""Latency / efficiency / memory benchmarks - results land in summary.md."""
import pytest


def test_benchmark(dut, model_name):
    m = dut.require_model(model_name)
    n = 3 if dut.quick else 20
    r = dut.device.bench(model_name, n=n, warmup=1, timeout=600)
    dut.record("bench", model=model_name, **{k: v for k, v in r.items() if k not in ("id", "ok", "model")},
                     cpu_mhz=dut.info.get("cpu_mhz"))
    assert r["stable"], "output changed between identical runs (memory corruption?)"
    assert r["us_min"] <= r["us_avg"] <= r["us_max"]
    if dut.info.get("has_cycles"):
        assert r["cyc_avg"] > 0
    assert m["macs"] == r["macs"]

    budget = dut.target.budgets.get(model_name)
    if budget is not None:
        assert r["us_avg"] <= budget, f"{r['us_avg']} µs exceeds the budget of {budget} µs"

    if dut.baseline and dut.target.transport != "process":
        ref = dut.baseline.get("perf", {}).get(dut.board.id, {}).get(model_name)
        if ref:
            tol = dut.options["tolerance"]
            assert r["us_avg"] <= ref["us_avg"] * (1 + tol), \
                f"latency regression: {r['us_avg']} µs vs baseline {ref['us_avg']} µs"


def test_no_heap_leak(dut, model_name):
    dut.require_model(model_name)
    before = dut.device.mem()["free_heap"]
    dut.device.bench(model_name, n=3, warmup=0, timeout=300)
    after = dut.device.mem()["free_heap"]
    if before == 0:
        pytest.skip("heap statistics not available on this target")
    assert after >= before - 64, f"free heap dropped {before} -> {after}"


def test_memory_headroom(dut):
    mem = dut.device.mem()
    dut.record("memory", **{k: v for k, v in mem.items() if k not in ("id", "ok")})
    if mem["free_heap"] == 0:
        pytest.skip("heap statistics not available on this target")
    assert mem["min_free_heap"] == 0 or mem["min_free_heap"] > 4096, "less than 4 KiB heap left at some point"
