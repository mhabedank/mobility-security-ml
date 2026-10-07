"""hilbench command line.

  hilbench discover [--probe]        find boards on USB, suggest boards.yaml entries
  hilbench list                      inventory + connection status
  hilbench doctor                    check tools, permissions, boards, firmware artifacts
  hilbench build [-t T ...]          build firmware for targets
  hilbench flash -b BOARD            flash one board
  hilbench info -b BOARD             INFO + MODELS of a running board
  hilbench console -b BOARD          interactive protocol console
  hilbench reset -b BOARD [--method] reset a board
  hilbench power -b BOARD on|off|cycle
  hilbench run [...] [-- PYTEST ARGS] build, flash and run the HIL test-suite
  hilbench report RUN_DIR            re-render summary.md / compare to a baseline
  hilbench zoo                       rebuild the reference model zoo + firmware sources
  hilbench import-tflite M.tflite    add your own int8 TFLite model to all boards
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .build import BuildError, build, new_build_id
from .config import REPO_ROOT, ConfigError, load_lab
from .discovery import DiscoveryError, esptool_probe, guess_targets, list_ports, match_probe, resolve_port
from .flash import Firmware, FlashError
from .power import PowerError, make_power
from .results import compare_to_baseline, render_markdown, write_summary
from .session import BoardSession, SessionError


def _lab(args):
    return load_lab(args.boards, args.targets_file)


def _available(board) -> tuple[bool, str]:
    if board.target.transport == "process":
        return True, "simulator"
    try:
        return True, resolve_port(board)
    except DiscoveryError as e:
        return False, str(e)


def cmd_discover(args):
    lab = _lab(args)
    ports = list_ports()
    if not ports:
        print("no USB serial ports found")
        return 0
    known = {}
    for b in lab.boards:
        if b.target.transport == "process":
            continue
        try:
            known[resolve_port(b, ports)] = b.id
        except DiscoveryError:
            pass
    suggestions = []
    for p in ports:
        guesses = guess_targets(p, lab.targets)
        chip = None
        if args.probe and p.device not in known and any(lab.targets[g].esptool_chip for g in guesses):
            chip = esptool_probe(p.device)
            if chip:
                guesses = match_probe(chip, lab.targets) or guesses
        print(f"{p.device}")
        for k, v in p.as_dict().items():
            if k != "device" and v:
                print(f"    {k:14s} {v}")
        if chip:
            print(f"    {'esptool chip':14s} {chip}")
        print(f"    {'targets':14s} {', '.join(guesses) or '?'}")
        if p.device in known:
            print(f"    {'inventory':14s} board '{known[p.device]}'")
        else:
            match = {"serial_number": p.serial_number} if p.serial_number else {"location": p.location}
            if not any(match.values()):
                match = {"vid_pid": p.vid_pid}
            suggestions.append({"id": f"{(guesses or ['board'])[0]}-{len(suggestions) + 1}",
                                "target": (guesses or ["?"])[0], "match": match})
    if suggestions:
        import yaml

        print("\n# suggested entries for hil/boards.yaml (check the target!):")
        print(yaml.safe_dump({"boards": suggestions}, sort_keys=False))
    return 0


def cmd_doctor(args):
    import importlib.util
    import os
    import shutil

    lab = _lab(args)
    problems = 0

    def check(ok: bool, msg: str, hint: str = "", hard: bool = True):
        nonlocal problems
        mark = "ok  " if ok else ("FAIL" if hard else "warn")
        print(f"[{mark}] {msg}" + (f"\n       -> {hint}" if not ok and hint else ""))
        if not ok and hard:
            problems += 1

    boards = lab.select()
    hw = [b for b in boards if b.target.transport != "process"]
    check(bool(shutil.which("make") and (shutil.which("cc") or shutil.which("gcc"))),
          "make + C compiler (simulator)", "install build-essential / gcc", hard=False)
    if any(b.target.build == "platformio" for b in hw):
        has_pio = shutil.which("pio") or importlib.util.find_spec("platformio")
        check(bool(has_pio), "PlatformIO", "pip install -e '.[hw]'  (or pip install platformio)")
    if any(b.flash_method == "esptool" for b in hw):
        check(importlib.util.find_spec("esptool") is not None, "esptool", "pip install esptool")
    if any(b.power.get("type") == "uhubctl" for b in hw):
        check(bool(shutil.which("uhubctl")), "uhubctl (USB port power)", "apt install uhubctl")
    if len(hw) > 1:
        check(importlib.util.find_spec("xdist") is not None, "pytest-xdist (parallel boards)",
              "pip install pytest-xdist", hard=False)
    if sys.platform.startswith("linux") and hw:
        import grp

        try:
            groups = {grp.getgrgid(g).gr_name for g in os.getgroups()}
            check("dialout" in groups or os.geteuid() == 0, "user is in group dialout",
                  "sudo ./hil/setup-host.sh, then log in again", hard=False)
        except KeyError:
            pass
    for b in boards:
        ok, where = _available(b)
        if b.target.transport != "process" and ok and not where.startswith(("rfc2217:", "socket:")):
            check(os.access(where, os.R_OK | os.W_OK), f"{b.id}: connected at {where}, read/write access",
                  "udev rules / dialout group (hil/setup-host.sh)")
        else:
            check(ok, f"{b.id}: {'available' if ok else 'not connected'} ({b.target.name})",
                  "hilbench discover", hard=False)
        try:
            fw = Firmware.load(lab, b.target.name)
            check(True, f"{b.id}: firmware artifact {fw.build_id:08x} ({fw.manifest.get('git', '?')})")
        except FlashError:
            check(False, f"{b.id}: no firmware built yet", f"hilbench build -t {b.target.name}", hard=False)
    print("\nall good" if not problems else f"\n{problems} problem(s)")
    return 1 if problems else 0


def cmd_list(args):
    lab = _lab(args)
    print(f"lab: {lab.name}   results: {lab.results_dir}")
    for b in lab.boards:
        ok, where = _available(b)
        state = "ok " if ok else "-- "
        flag = "" if b.enabled else " (disabled)"
        print(f"  [{state}] {b.id:16s} {b.target.name:16s} {where if ok else 'not connected'}{flag}")
    return 0


def cmd_targets(args):
    lab = _lab(args)
    for t in lab.targets.values():
        print(f"{t.name:16s} {t.description}")
    return 0


def _select_targets(lab, args):
    if args.target:
        missing = [t for t in args.target if t not in lab.targets]
        if missing:
            raise ConfigError(f"unknown target(s): {', '.join(missing)}")
        return [lab.targets[t] for t in args.target]
    if getattr(args, "all", False):
        return list(lab.targets.values())
    seen = {}
    for b in lab.select():
        seen.setdefault(b.target.name, b.target)
    return list(seen.values())


def cmd_build(args):
    lab = _lab(args)
    failures = 0
    for t in _select_targets(lab, args):
        print(f"building {t.name} ...", flush=True)
        try:
            fw = build(lab, t, verbose=args.verbose)
            print(f"  ok  {fw.dir}  build {fw.build_id:08x}")
        except BuildError as e:
            failures += 1
            print(f"  FAILED: {e}")
    return 1 if failures else 0


def _session(args, flash: bool):
    lab = _lab(args)
    board = lab.board(args.board)
    fw = None
    try:
        fw = Firmware.load(lab, board.target.name)
    except FlashError:
        if flash or board.target.transport == "process":
            fw = build(lab, board.target)
    return BoardSession(lab, board, fw, flash=flash, log_dir=lab.results_dir / "manual")


def cmd_flash(args):
    with _session(args, flash=True) as s:
        print(json.dumps(s.info, indent=2))
        print("\n".join(s.events))
    return 0


def cmd_info(args):
    s = _session(args, flash=False)
    s.firmware = None if s.target.transport != "process" else s.firmware  # no build check
    with s:
        print(json.dumps({"port": s.port, **s.info}, indent=2))
        for m in s.device.models():
            print(f"  model {m['idx']}: {m['name']:16s} in={m['in']:4d} out={m['out']:3d} "
                  f"macs={m['macs']:7d} params={m['params']:6d} B arena={m['arena']:5d} B crc={m['crc']}")
    return 0


def cmd_console(args):
    s = _session(args, flash=False)
    s.firmware = None if s.target.transport != "process" else s.firmware
    with s:
        print(f"connected to {args.board} ({s.port or 'simulator'}). Commands: PING INFO MODELS "
              "INFER <m> <hex> BENCH <m> <n> SELFTEST <m> VERIFY <m> MEM ECHO <hex> RESET. Ctrl-D quits.")
        for line in sys.stdin:
            parts = line.split()
            if not parts:
                continue
            try:
                r = s.device.request(parts[0].upper(), *parts[1:], timeout=60, allow_reset=True)
                print(json.dumps(r))
            except Exception as e:  # interactive: show and continue
                print(f"error: {e}")
    return 0


def cmd_reset(args):
    s = _session(args, flash=False)
    s.firmware = None if s.target.transport != "process" else s.firmware
    with s:
        boot = s.reset(args.method)
        print(json.dumps(boot or {"ready": True}))
    return 0


def cmd_power(args):
    lab = _lab(args)
    board = lab.board(args.board)
    p = make_power(board.power)
    getattr(p, args.action)()
    return 0


def cmd_run(args, pytest_args):
    import pytest

    lab = _lab(args)
    boards = lab.select(args.board or None, args.target or None, args.tag or None)
    available, missing = [], []
    for b in boards:
        ok, why = _available(b)
        (available if ok else missing).append((b, why))
    for b, why in missing:
        print(f"skip {b.id}: {why}")
    if not available:
        print("no boards available")
        return 1 if args.require_all or not boards else 0

    # One build per target, shared by all boards of that target.
    if not args.no_build:
        done = set()
        for b, _ in available:
            if b.target.name in done or (args.no_flash and b.target.build != "native"):
                continue
            print(f"building {b.target.name} ...", flush=True)
            try:
                build(lab, b.target, build_id=new_build_id())
            except BuildError as e:
                print(f"build failed for {b.target.name}:\n{e}")
                return 2
            done.add(b.target.name)

    run_dir = Path(args.results) if args.results else None
    argv = [args.tests or str(REPO_ROOT / "tests" / "hil"), "-p", "no:cacheprovider", "--hil-build=never",
            f"--hil-tolerance={args.tolerance}"]
    if args.boards:
        argv.append(f"--hil-boards={args.boards}")
    if args.targets_file:
        argv.append(f"--hil-targets-file={args.targets_file}")
    for b, _ in available:
        argv.append(f"--hil-board={b.id}")
    if args.no_flash:
        argv.append("--hil-no-flash")
    if args.quick:
        argv.append("--hil-quick")
    if args.require_all:
        argv.append("--hil-require-all")
    if args.baseline:
        argv.append(f"--hil-baseline={args.baseline}")
    if run_dir:
        argv.append(f"--hil-results={run_dir}")
    if not args.slow:
        argv += ["-m", "not slow"]
    if args.parallel and len(available) > 1:
        argv += ["-n", str(len(available)), "--dist", "loadgroup"]
    if args.junit:
        argv.append(f"--junitxml={args.junit}")
    argv += pytest_args
    print("pytest " + " ".join(argv), flush=True)
    return int(pytest.main(argv))


def cmd_report(args):
    summary = write_summary(Path(args.run_dir))
    print(render_markdown(summary))
    if args.baseline:
        base = json.loads(Path(args.baseline).read_text())
        regressions = compare_to_baseline(summary, base, args.tolerance)
        for r in regressions:
            print(f"REGRESSION {r}")
        return 1 if regressions else 0
    return 0


def cmd_zoo(args):
    from .ml import zoo

    zoo.main(["--codegen-only"] if args.codegen_only else [])
    return 0


def cmd_import_tflite(args):
    from .ml import tflite_import
    from .ml.codegen import write_zoo_sources
    from .ml.zoo import CUSTOM_DIR, FW_ZOO_DIR, load_zoo

    name = args.name or Path(args.model).stem
    try:
        qm = tflite_import.load_tflite(args.model, name, args.description or "")
    except tflite_import.UnsupportedModel as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(json.dumps(qm.summary(), indent=2))
    if args.verify:
        bad = tflite_import.verify_with_interpreter(args.model, qm)
        print(f"TFLite interpreter comparison: {32 - bad}/32 bit-exact")
        if bad:
            return 1
    CUSTOM_DIR.mkdir(parents=True, exist_ok=True)
    qm.save(CUSTOM_DIR / f"{name}.npz")
    write_zoo_sources(list(load_zoo().values()), FW_ZOO_DIR)
    print(f"saved {CUSTOM_DIR / (name + '.npz')} and regenerated firmware/lib/modelzoo "
          "- rebuild firmware (hilbench run does that) to deploy it")
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    pytest_args = []
    if "--" in argv:
        i = argv.index("--")
        argv, pytest_args = argv[:i], argv[i + 1:]

    ap = argparse.ArgumentParser(prog="hilbench", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", action="version", version=__version__)
    ap.add_argument("--boards", help="lab inventory (default hil/boards.yaml or $HILBENCH_BOARDS)")
    ap.add_argument("--targets-file", help="target catalogue (default hil/targets.yaml)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("discover", help="list USB serial devices and suggest inventory entries")
    p.add_argument("--probe", action="store_true", help="ask ESP ROM bootloaders for the chip type (resets them)")
    p.set_defaults(fn=cmd_discover)
    sub.add_parser("list", help="inventory and connection status").set_defaults(fn=cmd_list)
    sub.add_parser("doctor", help="check host prerequisites and boards").set_defaults(fn=cmd_doctor)
    sub.add_parser("targets", help="known targets").set_defaults(fn=cmd_targets)

    p = sub.add_parser("build", help="build firmware")
    p.add_argument("-t", "--target", action="append", default=[])
    p.add_argument("--all", action="store_true", help="all targets in the catalogue")
    p.add_argument("-v", "--verbose", action="store_true")
    p.set_defaults(fn=cmd_build)

    for name, fn, hlp in (("flash", cmd_flash, "flash a board"), ("info", cmd_info, "show INFO/MODELS"),
                          ("console", cmd_console, "interactive console")):
        p = sub.add_parser(name, help=hlp)
        p.add_argument("-b", "--board", required=True)
        p.set_defaults(fn=fn)

    p = sub.add_parser("reset", help="reset a board")
    p.add_argument("-b", "--board", required=True)
    p.add_argument("--method", help="override reset method")
    p.set_defaults(fn=cmd_reset)

    p = sub.add_parser("power", help="switch board power")
    p.add_argument("-b", "--board", required=True)
    p.add_argument("action", choices=["on", "off", "cycle"])
    p.set_defaults(fn=cmd_power)

    p = sub.add_parser("run", help="build, flash and test (extra pytest args after --)")
    p.add_argument("-b", "--board", action="append", default=[])
    p.add_argument("-t", "--target", action="append", default=[])
    p.add_argument("--tag", action="append", default=[])
    p.add_argument("--tests", help="test path (default tests/hil)")
    p.add_argument("--quick", action="store_true", help="smoke run with fewer iterations")
    p.add_argument("--slow", action="store_true", help="include slow soak tests")
    p.add_argument("--no-build", action="store_true", help="use existing firmware artifacts")
    p.add_argument("--no-flash", action="store_true", help="test the firmware already on the boards")
    p.add_argument("--parallel", action="store_true", help="test boards in parallel (pytest-xdist)")
    p.add_argument("--require-all", action="store_true", help="fail if a selected board is missing")
    p.add_argument("--baseline", help="summary.json to compare latency against")
    p.add_argument("--tolerance", type=float, default=0.25)
    p.add_argument("--results", help="run directory")
    p.add_argument("--junit", help="JUnit XML output path")
    p.set_defaults(fn=None)

    p = sub.add_parser("report", help="render the summary of a run")
    p.add_argument("run_dir")
    p.add_argument("--baseline")
    p.add_argument("--tolerance", type=float, default=0.25)
    p.set_defaults(fn=cmd_report)

    p = sub.add_parser("zoo", help="rebuild model zoo and firmware model sources")
    p.add_argument("--codegen-only", action="store_true")
    p.set_defaults(fn=cmd_zoo)

    p = sub.add_parser("import-tflite", help="add an int8 .tflite model to the firmware")
    p.add_argument("model")
    p.add_argument("--name", help="model name (default: file name)")
    p.add_argument("--description")
    p.add_argument("--verify", action="store_true", help="compare with the TFLite interpreter (needs tensorflow)")
    p.set_defaults(fn=cmd_import_tflite)

    args = ap.parse_args(argv)
    try:
        if args.cmd == "run":
            return cmd_run(args, pytest_args)
        return args.fn(args)
    except (ConfigError, DiscoveryError, BuildError, FlashError, SessionError, PowerError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
