"""Selective extraction of members from a remote zip via HTTP ranges (no network)."""
import io
import zipfile

import pytest

from hilbench.data import download as dl


@pytest.fixture
def remote_zip(monkeypatch):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for i in range(30):
            z.writestr(f"fan/id_00/normal/{i:08d}.wav", bytes([i]) * (5000 + i), compress_type=zipfile.ZIP_DEFLATED)
        for i in range(10):
            z.writestr(f"fan/id_00/abnormal/{i:08d}.wav", bytes(range(256)) * (i + 1),
                       compress_type=zipfile.ZIP_STORED)
        z.writestr("fan/../../evil.wav", b"x")
    blob = buf.getvalue()
    requests = []

    def fake_range_get(url, start, end, retries=4):
        requests.append((start, end))
        return blob[start:end + 1]

    monkeypatch.setattr(dl, "_range_get", fake_range_get)
    return dl.RemoteFile(url="https://example.invalid/fan.zip", name="fan.zip", size=len(blob)), requests


def test_fetch_selected_members(tmp_path, remote_zip):
    f, requests = remote_zip
    sel = (("*/normal/*.wav", 5), ("*/abnormal/*.wav", 3))
    assert dl.fetch_zip_members(f, tmp_path, sel, workers=2) == 8
    normal = sorted((tmp_path / "fan/id_00/normal").iterdir())
    abnormal = sorted((tmp_path / "fan/id_00/abnormal").iterdir())
    assert len(normal) == 5 and len(abnormal) == 3
    i = int(normal[0].stem)
    assert normal[0].read_bytes() == bytes([i]) * (5000 + i)
    j = int(abnormal[0].stem)
    assert abnormal[0].read_bytes() == bytes(range(256)) * (j + 1)
    # second run is a no-op and the selection is deterministic
    n_req = len(requests)
    assert dl.fetch_zip_members(f, tmp_path, sel, workers=2) == 0
    assert sorted((tmp_path / "fan/id_00/normal").iterdir()) == normal
    assert len(requests) - n_req <= 3  # only the central directory


def test_unsafe_member_path_rejected(tmp_path, remote_zip):
    f, _ = remote_zip
    with pytest.raises(dl.DataError, match="unsafe path"):
        dl.fetch_zip_members(f, tmp_path, (("*evil.wav", 1),))


@pytest.mark.parametrize("kind", ["tar.gz", "zip"])
def test_empty_zip_wrapper_with_embedded_archive(tmp_path, kind):
    """UCI sometimes serves an empty zip with the real archive appended."""
    import tarfile

    src = tmp_path / "src"
    (src / "set").mkdir(parents=True)
    (src / "set" / "a.log").write_text("(1.0) can0 123#00\n")
    payload = tmp_path / f"p.{kind}"
    if kind == "zip":
        with zipfile.ZipFile(payload, "w") as z:
            z.write(src / "set" / "a.log", "set/a.log")
    else:
        with tarfile.open(payload, "w:gz") as t:
            t.add(src / "set", arcname="set")
    empty = io.BytesIO()
    zipfile.ZipFile(empty, "w").close()
    assert len(empty.getvalue()) == 22
    wrapped = tmp_path / "raw" / "ds.zip"
    wrapped.parent.mkdir()
    wrapped.write_bytes(empty.getvalue() + payload.read_bytes() + b"\0" * 2048)
    dl._extract(wrapped, tmp_path / "out")
    assert (tmp_path / "out" / "set" / "a.log").read_text().startswith("(1.0)")
