"""Streaming audio features computed in one pass over decoded PCM.

The decoder delivers 16-bit stereo blocks; nothing here keeps the whole track in
memory. Three feature families are accumulated side by side:

* min/max amplitude bins of 20 ms, the basis of the stored waveform;
* an onset-strength envelope (log-compressed spectral flux), used for tempo;
* a 36-bin pitch-class profile from spectral peaks, used for the key.

Every step is vectorised NumPy, so the heavy work releases the interpreter lock
between blocks and the graphical thread keeps its frame rate.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

__all__ = [
    "CHROMA_FFT",
    "CHROMA_HOP",
    "ENVELOPE_RATE",
    "ONSET_FFT",
    "ONSET_HOP",
    "SAMPLE_RATE",
    "WAVEFORM_BIN_FRAMES",
    "AudioFeatures",
    "FeatureExtractor",
]

SAMPLE_RATE = 22_050
ONSET_FFT = 1024
ONSET_HOP = 256
ENVELOPE_RATE = SAMPLE_RATE / ONSET_HOP
CHROMA_FFT = 4096
CHROMA_HOP = 2048
WAVEFORM_BIN_FRAMES = 441  # 20 ms at 22 050 Hz

_CHROMA_LOW_HZ = 80.0
_CHROMA_HIGH_HZ = 5_000.0
_CHROMA_BINS_PER_SEMITONE = 3
_REFERENCE_A_HZ = 440.0
_ONSET_GAIN = 40.0
_ONSET_BAND_COUNT = 28


@dataclass(frozen=True, slots=True)
class AudioFeatures:
    """Features of a whole track; arrays are empty when nothing was decoded."""

    frames: int
    waveform_low: np.ndarray
    waveform_high: np.ndarray
    onset_envelope: np.ndarray
    pitch_profile: np.ndarray

    @property
    def duration_us(self) -> int:
        return round(self.frames * 1_000_000 / SAMPLE_RATE)


class _Framer:
    """Cut a stream of samples into overlapping frames without copying the tail."""

    def __init__(self, size: int, hop: int) -> None:
        self._size = size
        self._hop = hop
        self._buffer = np.zeros(0, dtype=np.float32)

    def push(self, samples: np.ndarray) -> np.ndarray | None:
        buffer = np.concatenate((self._buffer, samples)) if self._buffer.size else samples
        if buffer.size < self._size:
            self._buffer = buffer
            return None
        count = 1 + (buffer.size - self._size) // self._hop
        frames = np.lib.stride_tricks.sliding_window_view(buffer, self._size)[:: self._hop][:count]
        self._buffer = buffer[count * self._hop :].copy()
        return frames


def _onset_band_matrix() -> np.ndarray:
    """Return a (513, bands) matrix grouping FFT bins into log-spaced bands."""
    bins = ONSET_FFT // 2 + 1
    edges = np.unique(np.round(np.geomspace(1, bins - 1, _ONSET_BAND_COUNT + 1)).astype(int))
    matrix = np.zeros((bins, len(edges) - 1), dtype=np.float32)
    for band in range(len(edges) - 1):
        matrix[edges[band] : edges[band + 1], band] = 1.0
    matrix[bins - 1, -1] = 1.0
    return matrix


class FeatureExtractor:
    """Accumulate waveform, tempo and key features from PCM blocks."""

    def __init__(self, *, rhythm: bool = True, tonality: bool = True) -> None:
        self._rhythm = rhythm
        self._tonality = tonality
        self._frames = 0
        self._carry = np.zeros((0, 2), dtype=np.int16)
        self._low: list[np.ndarray] = []
        self._high: list[np.ndarray] = []
        self._onset_framer = _Framer(ONSET_FFT, ONSET_HOP)
        self._onset_window = np.hanning(ONSET_FFT).astype(np.float32)
        self._onset_bands = _onset_band_matrix()
        self._previous_log: np.ndarray | None = None
        self._envelope: list[np.ndarray] = []
        self._chroma_framer = _Framer(CHROMA_FFT, CHROMA_HOP)
        self._chroma_window = np.hanning(CHROMA_FFT).astype(np.float32)
        self._pitch_profile = np.zeros(12 * _CHROMA_BINS_PER_SEMITONE, dtype=np.float64)
        frequencies = np.fft.rfftfreq(CHROMA_FFT, 1.0 / SAMPLE_RATE)
        self._chroma_first = int(np.searchsorted(frequencies, _CHROMA_LOW_HZ))
        self._chroma_last = int(np.searchsorted(frequencies, _CHROMA_HIGH_HZ))
        self._chroma_frequencies = frequencies

    @property
    def frames(self) -> int:
        return self._frames

    def feed(self, block: bytes | np.ndarray) -> None:
        """Consume one block of interleaved signed 16-bit little-endian stereo PCM."""
        if isinstance(block, np.ndarray):
            pcm = block.reshape(-1, 2).astype(np.int16, copy=False)
        else:
            pcm = np.frombuffer(block, dtype="<i2").reshape(-1, 2)
        if pcm.shape[0] == 0:
            return
        self._frames += pcm.shape[0]
        self._add_waveform(pcm)
        if self._rhythm or self._tonality:
            mono = pcm.astype(np.float32).mean(axis=1) * np.float32(1.0 / 32768.0)
            if self._rhythm:
                self._add_onsets(mono)
            if self._tonality:
                self._add_chroma(mono)

    def finish(self) -> AudioFeatures:
        """Flush the partial waveform bin and return every accumulated feature."""
        if self._carry.shape[0]:
            self._low.append(np.array([self._carry.min()], dtype=np.int16))
            self._high.append(np.array([self._carry.max()], dtype=np.int16))
            self._carry = self._carry[:0]
        empty = np.zeros(0, dtype=np.int16)
        return AudioFeatures(
            frames=self._frames,
            waveform_low=np.concatenate(self._low) if self._low else empty,
            waveform_high=np.concatenate(self._high) if self._high else empty,
            onset_envelope=(
                np.concatenate(self._envelope) if self._envelope else np.zeros(0, dtype=np.float32)
            ),
            pitch_profile=self._pitch_profile.copy(),
        )

    # ------------------------------------------------------------- waveform

    def _add_waveform(self, pcm: np.ndarray) -> None:
        data = np.concatenate((self._carry, pcm)) if self._carry.shape[0] else pcm
        whole = (data.shape[0] // WAVEFORM_BIN_FRAMES) * WAVEFORM_BIN_FRAMES
        if whole:
            bins = data[:whole].reshape(-1, WAVEFORM_BIN_FRAMES * 2)
            self._low.append(bins.min(axis=1))
            self._high.append(bins.max(axis=1))
        self._carry = data[whole:].copy()

    # ---------------------------------------------------------------- tempo

    def _add_onsets(self, mono: np.ndarray) -> None:
        frames = self._onset_framer.push(mono)
        if frames is None:
            return
        spectrum = np.abs(np.fft.rfft(frames * self._onset_window, axis=1))
        bands = spectrum.astype(np.float32) @ self._onset_bands
        compressed = np.log1p(bands * np.float32(_ONSET_GAIN))
        if self._previous_log is not None:
            compressed = np.vstack((self._previous_log, compressed))
        elif compressed.shape[0] > 1:
            compressed = np.vstack((compressed[:1], compressed))
        else:
            self._previous_log = compressed[-1:]
            return
        self._previous_log = compressed[-1:]
        flux = np.maximum(np.diff(compressed, axis=0), 0.0).sum(axis=1)
        self._envelope.append(flux.astype(np.float32))

    # ------------------------------------------------------------------ key

    def _add_chroma(self, mono: np.ndarray) -> None:
        frames = self._chroma_framer.push(mono)
        if frames is None:
            return
        magnitude = np.abs(np.fft.rfft(frames * self._chroma_window, axis=1)).astype(np.float32)
        first, last = self._chroma_first, self._chroma_last
        band = magnitude[:, first - 1 : last + 1]
        centre = band[:, 1:-1]
        peaks = (centre > band[:, :-2]) & (centre >= band[:, 2:])
        loudest = centre.max(axis=1, keepdims=True)
        peaks &= centre > loudest * 0.02
        rows, columns = np.nonzero(peaks)
        if rows.size == 0:
            return
        left = band[rows, columns]
        middle = band[rows, columns + 1]
        right = band[rows, columns + 2]
        denominator = left - 2.0 * middle + right
        offset = np.where(
            np.abs(denominator) > 1e-12, 0.5 * (left - right) / denominator, 0.0
        ).clip(-0.5, 0.5)
        bin_index = first + columns + offset
        frequency = bin_index * (SAMPLE_RATE / CHROMA_FFT)
        semitones = 12.0 * np.log2(frequency / _REFERENCE_A_HZ)
        slot = np.round(semitones * _CHROMA_BINS_PER_SEMITONE).astype(np.int64)
        # Weight each peak by its compressed magnitude relative to its frame, so
        # one loud bass note cannot outvote the harmony of a whole passage.
        weight = np.sqrt(middle / loudest[rows, 0])
        self._pitch_profile += np.bincount(
            slot % (12 * _CHROMA_BINS_PER_SEMITONE),
            weights=weight.astype(np.float64),
            minlength=12 * _CHROMA_BINS_PER_SEMITONE,
        )
