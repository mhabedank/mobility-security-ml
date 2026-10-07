"""Feature extraction shared by training and the bench host (numpy only).

WAV reading and log-mel spectrograms (used by the machine-sound anomaly task).
Defaults: 16 kHz, 30 ms window, 20 ms hop, 40 mel bands (20 Hz - 4 kHz).
"""
from __future__ import annotations

import struct
from pathlib import Path

import numpy as np

SR = 16000
WIN = 480  # 30 ms
HOP = 320  # 20 ms
NFFT = 512
N_MELS = 40
FMIN, FMAX = 20.0, 4000.0


def read_wav(path, length: int = SR, channel: int | None = None) -> np.ndarray:
    """PCM wav (16/24/32 bit, plain or WAVE_FORMAT_EXTENSIBLE) -> mono float32 in [-1, 1],
    padded/cropped to `length` (0 = keep). Multi-channel files are averaged, or reduced to
    `channel` if given. Own RIFF parser: Python's `wave` rejects EXTENSIBLE before 3.12."""
    raw = Path(path).read_bytes()
    if raw[:4] != b"RIFF" or raw[8:12] != b"WAVE":
        raise ValueError(f"{path}: not a RIFF/WAVE file")
    fmt = data = None
    pos = 12
    while pos + 8 <= len(raw):
        cid, size = raw[pos:pos + 4], struct.unpack_from("<I", raw, pos + 4)[0]
        body = raw[pos + 8:pos + 8 + size]
        if cid == b"fmt ":
            fmt = body
        elif cid == b"data":
            data = body
            break
        pos += 8 + size + (size & 1)
    if fmt is None or data is None:
        raise ValueError(f"{path}: missing fmt or data chunk")
    tag, n_ch, _sr, _rate, _align, bits = struct.unpack_from("<HHIIHH", fmt)
    if tag == 0xFFFE and len(fmt) >= 26:  # EXTENSIBLE: sub-format GUID starts with the real tag
        tag = struct.unpack_from("<H", fmt, 24)[0]
    if tag != 1 or bits not in (16, 24, 32):
        raise ValueError(f"{path}: unsupported wav format (tag {tag}, {bits} bit)")
    width = bits // 8
    n = len(data) // (width * n_ch) * n_ch
    if width == 3:
        b = np.frombuffer(data[:n * 3], dtype=np.uint8).reshape(-1, 3)
        hi = b[:, 2].astype(np.int8).astype(np.int32)  # sign-extend the top byte
        x = b[:, 0].astype(np.int32) | (b[:, 1].astype(np.int32) << 8) | (hi << 16)
        x = x.astype(np.float32) / float(1 << 23)
    else:
        x = np.frombuffer(data[:n * width], dtype="<i2" if width == 2 else "<i4").astype(np.float32)
        x /= float(1 << (bits - 1))
    if n_ch > 1:
        x = x.reshape(-1, n_ch)
        x = x.mean(axis=1) if channel is None else x[:, channel]
    if length:
        x = x[:length] if len(x) >= length else np.pad(x, (0, length - len(x)))
    return x.astype(np.float32)


def _hz_to_mel(f):
    return 2595.0 * np.log10(1.0 + np.asarray(f) / 700.0)


def _mel_to_hz(m):
    return 700.0 * (10 ** (np.asarray(m) / 2595.0) - 1.0)


def mel_filterbank(n_mels: int = N_MELS, nfft: int = NFFT, sr: int = SR, fmin: float = FMIN,
                   fmax: float = FMAX) -> np.ndarray:
    mels = np.linspace(_hz_to_mel(fmin), _hz_to_mel(fmax), n_mels + 2)
    bins = np.floor((nfft + 1) * _mel_to_hz(mels) / sr).astype(int)
    fb = np.zeros((n_mels, nfft // 2 + 1), dtype=np.float32)
    for i in range(n_mels):
        lo, c, hi = bins[i], bins[i + 1], bins[i + 2]
        if c > lo:
            fb[i, lo:c] = (np.arange(lo, c) - lo) / (c - lo)
        if hi > c:
            fb[i, c:hi] = (hi - np.arange(c, hi)) / (hi - c)
    return fb


_FB = mel_filterbank()
_WINDOW = np.hanning(WIN).astype(np.float32)


def frames(x: np.ndarray, win: int = WIN, hop: int = HOP) -> np.ndarray:
    n = 1 + (len(x) - win) // hop
    idx = np.arange(win)[None, :] + hop * np.arange(n)[:, None]
    return x[idx]


def log_mel(x: np.ndarray, n_mels: int = N_MELS, win: int = WIN, hop: int = HOP, nfft: int = NFFT,
            sr: int = SR, fmax: float = FMAX) -> np.ndarray:
    fb = _FB if (n_mels, nfft, sr, fmax) == (N_MELS, NFFT, SR, FMAX) else mel_filterbank(n_mels, nfft, sr,
                                                                                          FMIN, fmax)
    window = _WINDOW if win == WIN else np.hanning(win).astype(np.float32)
    spec = np.abs(np.fft.rfft(frames(x, win, hop) * window, n=nfft)) ** 2
    return np.log(spec @ fb.T + 1e-6).astype(np.float32)
