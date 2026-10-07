"""pytest integration: every test that requests `dut` runs once per selected board.

    pytest tests/hil                           # all enabled boards in hil/boards.yaml
    pytest tests/hil --hil-board esp8266-1     # one board
    pytest tests/hil --hil-target esp32 -n 4 --dist loadgroup   # boards in parallel

Boards that are not connected are skipped (or fail with --hil-require-all).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from .build import BuildError, build
from .config import Board, ConfigError, Lab, load_lab
from .device import Device
from .discovery import DiscoveryError, resolve_port
from .flash import Firmware, FlashError
from .lock import BoardLock
from .results import Recorder, compare_to_baseline, new_run_dir, render_markdown, write_summary
from .session import BoardSession, SessionError
from .transport import TransportError


def pytest_addoption(parser):
    g = parser.getgroup("hil", "hardware-in-the-loop bench")
    g.addoption("--hil-boards", default=None, help="lab inventory (default: hil/boards.yaml or $HILBENCH_BOARDS)")
    g.addoption("--hil-targets-file", default=None, help="target catalogue (default: hil/targets.yaml)")
    g.addoption("--hil-board", action="append", default=[], help="only this board id (repeatable)")
    g.addoption("--hil-target", action="append", default=[], help="only boards of this target (repeatable)")
    g.addoption("--hil-tag", action="append", default=[], help="only boards with this tag (repeatable)")
    g.addoption("--hil-build", choices=["auto", "always", "never"], default="auto",
                help="build firmware: auto = only if no artifact exists (default)")
    g.addoption("--hil-no-flash", action="store_true", help="do not flash; test what is on the board")
    g.addoption("--hil-require-all", action="store_true", help="fail (instead of skip) if a board is missing")
    g.addoption("--hil-results", default=None, help="run directory (default: <results_dir>/<timestamp>)")
    g.addoption("--hil-baseline", default=None, help="summary.json of a previous run for regression checks")
    g.addoption("--hil-tolerance", type=float, default=0.25, help="allowed latency regression (0.25 = +25%%)")
    g.addoption("--hil-quick", action="store_true", help="fewer iterations (smoke run)")


# ---------------------------------------------------------------- state --

@dataclass
class HilState:
    lab: Lab
    boards: list[Board]
    run_dir: Path
    recorder: Recorder
    options: dict
    node_board: dict = field(default_factory=dict)
    baseline: dict | None = None
    is_worker: bool = False


_STATE_KEY = pytest.StashKey[HilState]()


def _state(config) -> HilState:
    return config.stash[_STATE_KEY]


class _XdistHooks:
    """Only registered when pytest-xdist is active: share the run dir with workers."""

    def __init__(self, config):
        self.config = config

    @pytest.hookimpl(optionalhook=True)
    def pytest_configure_node(self, node):
        node.workerinput["hil_run_dir"] = str(_state(self.config).run_dir)


def pytest_configure(config):
    config.addinivalue_line("markers", "hil: test needs a device under test")
    config.addinivalue_line("markers", "slow: long running (soak) test")
    config.addinivalue_line("markers", "destructive: resets/power-cycles the board")
    try:
        lab = load_lab(config.getoption("--hil-boards"), config.getoption("--hil-targets-file"))
        boards = lab.select(config.getoption("--hil-board") or None, config.getoption("--hil-target") or None,
                            config.getoption("--hil-tag") or None)
    except ConfigError as e:
        raise pytest.UsageError(f"hilbench: {e}") from e

    workerinput = getattr(config, "workerinput", None)
    if workerinput is not None:
        run_dir = Path(workerinput["hil_run_dir"])
        worker = workerinput.get("workerid", "gw")
    else:
        opt = config.getoption("--hil-results")
        run_dir = Path(opt) if opt else new_run_dir(lab.results_dir)
        worker = "main"
        if config.pluginmanager.hasplugin("xdist"):
            config.pluginmanager.register(_XdistHooks(config), "hilbench-xdist")
    baseline = None
    if config.getoption("--hil-baseline"):
        baseline = json.loads(Path(config.getoption("--hil-baseline")).read_text())
    config.stash[_STATE_KEY] = HilState(
        lab=lab, boards=boards, run_dir=run_dir, recorder=Recorder(run_dir, worker), baseline=baseline,
        is_worker=workerinput is not None,
        options={k: config.getoption(f"--hil-{k.replace('_', '-')}")
                 for k in ("build", "no_flash", "require_all", "quick", "tolerance")})
    if not config.pluginmanager.hasplugin("xdist"):
        config.addinivalue_line("markers", "xdist_group(name): run tests of one board in one worker")


def pytest_generate_tests(metafunc):
    st = _state(metafunc.config)
    if "board" in metafunc.fixturenames:
        metafunc.parametrize("board", st.boards, ids=[b.id for b in st.boards], scope="session")
    if "model_name" in metafunc.fixturenames:
        names = _zoo_names()
        metafunc.parametrize("model_name", names, ids=names, scope="session")


def _zoo_names() -> list[str]:
    from .ml.zoo import ZOO_DIR

    manifest = json.loads((ZOO_DIR / "manifest.json").read_text())
    return [m["name"] for m in manifest["models"]]


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(config, items):
    st = _state(config)
    for item in items:
        callspec = getattr(item, "callspec", None)
        board = callspec.params.get("board") if callspec else None
        if board is not None:
            st.node_board[item.nodeid] = board.id
            item.add_marker(pytest.mark.hil)
            item.add_marker(pytest.mark.xdist_group(board.id))


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    st = _state(item.config)
    board = st.node_board.get(item.nodeid)
    if board is None:
        return
    dut = item.funcargs.get("dut") if hasattr(item, "funcargs") else None
    if rep.failed and isinstance(dut, DUT) and dut.device is not None:
        tail = "\n".join(dut.device.log_tail[-30:])
        if tail:
            rep.sections.append(("serial log (tail)", tail))
        if dut.session.events:
            rep.sections.append(("board events", "\n".join(dut.session.events[-20:])))
    if rep.when == "call" or (rep.when == "setup" and rep.outcome != "passed"):
        msg = ""
        if rep.failed:
            msg = str(rep.longrepr)[-2000:]
        elif rep.skipped and isinstance(rep.longrepr, tuple):
            msg = str(rep.longrepr[2])
        st.recorder.record("test", board, nodeid=item.nodeid, outcome=rep.outcome,
                           duration=round(rep.duration, 3), message=msg)


def pytest_sessionfinish(session, exitstatus):
    st = session.config.stash.get(_STATE_KEY, None)
    if st is None or st.is_worker or not (st.run_dir / "metrics").exists():
        return
    summary = write_summary(st.run_dir)
    if st.baseline:
        regressions = compare_to_baseline(summary, st.baseline, st.options["tolerance"])
        (st.run_dir / "regressions.json").write_text(json.dumps(regressions, indent=2) + "\n")
    gh = os.environ.get("GITHUB_STEP_SUMMARY")
    if gh:
        with open(gh, "a") as fh:
            fh.write(render_markdown(summary))


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    st = config.stash.get(_STATE_KEY, None)
    if st is None or st.is_worker or not (st.run_dir / "metrics").exists():
        return
    terminalreporter.write_sep("-", f"hilbench results: {st.run_dir}")
    md = st.run_dir / "summary.md"
    if md.exists():
        terminalreporter.write_line(md.read_text())


# -------------------------------------------------------------- fixtures --

class DUT:
    """Device under test handed to the tests."""

    def __init__(self, session: BoardSession, recorder: Recorder, options: dict, baseline: dict | None):
        self.session = session
        self.board = session.board
        self.target = session.target
        self.recorder = recorder
        self.options = options
        self.baseline = baseline
        self._models: dict | None = None

    @property
    def device(self) -> Device:
        return self.session.device

    @property
    def info(self) -> dict:
        return self.session.info

    @property
    def quick(self) -> bool:
        return bool(self.options.get("quick"))

    def models(self) -> dict[str, dict]:
        if self._models is None:
            self._models = {m["name"]: m for m in self.device.models()}
        return self._models

    def require_model(self, name: str) -> dict:
        m = self.models().get(name)
        if m is None:
            pytest.skip(f"model {name} not built for {self.target.name}")
        return m

    def record(self, kind: str, **data) -> dict:
        return self.recorder.record(kind, self.board.id, target=self.target.name, **data)


def _firmware_for(st: HilState, board: Board) -> Firmware | None:
    policy = st.options["build"]
    target = board.target
    if policy == "never" or (st.options["no_flash"] and target.build != "native"):
        try:
            return Firmware.load(st.lab, target.name)
        except FlashError:
            return None
    with BoardLock(st.lab.lock_dir, f"build-{target.name}", timeout=1800):
        if policy == "auto":
            try:
                return Firmware.load(st.lab, target.name)
            except FlashError:
                pass
        return build(st.lab, target)


@pytest.fixture(scope="session")
def hil(request) -> HilState:
    return _state(request.config)


# Board sessions live for the whole worker process: pytest(-xdist) may tear
# down and re-create session fixtures several times (batch boundaries), but a
# board must only be flashed once per run.
_SESSIONS: dict[str, DUT] = {}
_BROKEN: dict[str, tuple[str, str]] = {}  # board id -> (skip|fail, reason)


def _bring_up(st: HilState, board: Board) -> DUT:
    if board.target.transport != "process":
        try:
            resolve_port(board)
        except DiscoveryError as e:
            raise _Unavailable("fail" if st.options["require_all"] else "skip",
                               f"board {board.id} not connected: {e}") from e
    try:
        fw = _firmware_for(st, board)
    except BuildError as e:
        raise _Unavailable("fail", f"firmware build for {board.target.name} failed: {e}") from e
    session = BoardSession(st.lab, board, fw, flash=not st.options["no_flash"], log_dir=st.run_dir / "logs")
    try:
        session.__enter__()
    except (SessionError, FlashError, TransportError, DiscoveryError, OSError) as e:
        raise _Unavailable("fail", f"bringing up {board.id} failed: {e}") from e
    d = DUT(session, st.recorder, st.options, st.baseline)
    info = session.info
    d.record("board", **{k: info.get(k) for k in ("chip", "cpu_mhz", "build", "framework", "uid", "fw",
                                                    "free_heap", "has_cycles")},
             port=session.port, events=list(session.events))
    return d


class _Unavailable(Exception):
    def __init__(self, kind: str, reason: str):
        super().__init__(reason)
        self.kind = kind


@pytest.fixture(scope="session")
def dut(board: Board, hil: HilState):
    if board.id in _BROKEN:
        kind, reason = _BROKEN[board.id]
        (pytest.skip if kind == "skip" else pytest.fail)(reason)
    d = _SESSIONS.get(board.id)
    if d is not None:
        try:
            d.device.ping()
        except Exception as e:  # e.g. a previous test crashed it
            try:
                d.session.recover(f"unresponsive between tests: {e}")
            except SessionError as e2:
                _BROKEN[board.id] = ("fail", str(e2))
                _SESSIONS.pop(board.id).session.close()
                pytest.fail(str(e2))
    else:
        try:
            d = _SESSIONS[board.id] = _bring_up(hil, board)
        except _Unavailable as e:
            _BROKEN[board.id] = (e.kind, str(e))
            (pytest.skip if e.kind == "skip" else pytest.fail)(str(e))
    yield d


def pytest_unconfigure(config):
    while _SESSIONS:
        _, d = _SESSIONS.popitem()
        d.session.close()
