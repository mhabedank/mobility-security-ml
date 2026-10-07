"""Feature extraction shared by training and the bench host (numpy only).

MFCC parameters follow the MLPerf Tiny keyword-spotting reference:
16 kHz, 1 s clips, 30 ms window, 20 ms hop, 40 mel bands (20 Hz - 4 kHz),
10 cepstral coefficients -> 49 x 10 features.
"""
from __future__ import annotations

import wave

import numpy as np

SR = 16000
WIN = 480  # 30 ms
HOP = 320  # 20 ms
NFFT = 512
N_MELS = 40
N_MFCC = 10
FMIN, FMAX = 20.0, 4000.0


def read_wav(path, length: int = SR, channel: int | None = None) -> np.ndarray:
    """16-bit PCM wav -> mono float32 in [-1, 1], padded/cropped to `length`.
    Multi-channel files are averaged, or reduced to `channel` if given."""
    with wave.open(str(path), "rb") as w:
        if w.getsampwidth() != 2:
            raise ValueError(f"{path}: expected 16-bit PCM")
        x = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float32) / 32768.0
        if w.getnchannels() > 1:
            x = x.reshape(-1, w.getnchannels())
            x = x.mean(axis=1) if channel is None else x[:, channel]
    if length:
        x = x[:length] if len(x) >= length else np.pad(x, (0, length - len(x)))
    return x


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


def _dct_matrix(n_out: int, n_in: int) -> np.ndarray:
    k = np.arange(n_out)[:, None]
    n = np.arange(n_in)[None, :]
    m = np.cos(np.pi / n_in * (n + 0.5) * k) * np.sqrt(2.0 / n_in)
    m[0] /= np.sqrt(2.0)
    return m.astype(np.float32)


_FB = mel_filterbank()
_DCT = _dct_matrix(N_MFCC, N_MELS)
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


def mfcc(x: np.ndarray) -> np.ndarray:
    """1 s @16 kHz -> (49, 10) MFCC."""
    return log_mel(x) @ _DCT.T
