"""Integrated loudness (ITU-R BS.1770-4 / EBU R128) and sample peak, streamed over PCM.

The meter receives the stereo 16-bit blocks of the decoder, so it runs in the same pass as
the other analyses and keeps no more than one decoded block in memory.

K-weighting is the two-stage filter of BS.1770-4: a high shelf, then the RLB high-pass.
Its coefficients are derived for the sample rate in use from the analogue prototypes that
define the standard, by bilinear transform with pre-warping (the method of libebur128).
At 48 kHz they are the published coefficients; at the 22 050 Hz rate of the analysis they
are the same filter for that rate.

The IIR stages are applied as a convolution with their impulse response, truncated at
8192 samples: by then the response has decayed far below any audible or measurable level.
Overlap-save with FFTs keeps the work in NumPy, and the result does not depend on how the
stream is cut into blocks.

Gating follows the standard. 400 ms blocks are taken every 100 ms; a block is the sum of
four consecutive 100 ms hops, so the energy of each hop is all that is accumulated. Blocks
below -70 LUFS are discarded, then blocks more than 10 LU below the mean of the remaining
ones. Stereo channels have unit weight.
"""

from __future__ import annotations

import math

import numpy as np

from mtee.domain.loudness import LoudnessResult

__all__ = ["LoudnessMeter", "k_weighting_sections"]

_SHELF_FREQUENCY_HZ = 1681.974450955533
_SHELF_GAIN_DB = 3.999843853973347
_SHELF_Q = 0.7071752369554196
_SHELF_EXPONENT = 0.4996667741545416
_HIGHPASS_FREQUENCY_HZ = 38.13547087602444
_HIGHPASS_Q = 0.5003270373238773
_OFFSET_DB = -0.691
_ABSOLUTE_GATE_LUFS = -70.0
_RELATIVE_GATE_LU = -10.0
_BLOCK_HOPS = 4  # 400 ms made of 100 ms hops
_IMPULSE_LENGTH = 8192
_FULL_SCALE = 32768.0

Biquad = tuple[tuple[float, float, float], tuple[float, float, float]]


def k_weighting_sections(sample_rate: int) -> tuple[Biquad, Biquad]:
    """Return the ``(b, a)`` coefficients of the shelf and of the RLB high-pass.

    ``a[0]`` is 1. The stages are the standard's, so their response is the same whatever
    the sample rate, up to the accuracy of the bilinear transform.
    """
    if sample_rate <= 0:
        raise ValueError("the sample rate must be positive")
    k = math.tan(math.pi * _SHELF_FREQUENCY_HZ / sample_rate)
    high_gain = 10.0 ** (_SHELF_GAIN_DB / 20.0)
    band_gain = high_gain**_SHELF_EXPONENT
    a0 = 1.0 + k / _SHELF_Q + k * k
    shelf_b = (
        (high_gain + band_gain * k / _SHELF_Q + k * k) / a0,
        2.0 * (k * k - high_gain) / a0,
        (high_gain - band_gain * k / _SHELF_Q + k * k) / a0,
    )
    shelf_a = (1.0, 2.0 * (k * k - 1.0) / a0, (1.0 - k / _SHELF_Q + k * k) / a0)

    k = math.tan(math.pi * _HIGHPASS_FREQUENCY_HZ / sample_rate)
    a0 = 1.0 + k / _HIGHPASS_Q + k * k
    highpass_b = (1.0, -2.0, 1.0)
    highpass_a = (1.0, 2.0 * (k * k - 1.0) / a0, (1.0 - k / _HIGHPASS_Q + k * k) / a0)
    return (shelf_b, shelf_a), (highpass_b, highpass_a)


def _impulse_response(sample_rate: int) -> np.ndarray:
    """Return the K-weighting impulse response, truncated at ``_IMPULSE_LENGTH``."""
    signal = [0.0] * _IMPULSE_LENGTH
    signal[0] = 1.0
    for (b0, b1, b2), (_, a1, a2) in k_weighting_sections(sample_rate):
        previous = previous_2 = out_1 = out_2 = 0.0
        output = [0.0] * _IMPULSE_LENGTH
        for index, value in enumerate(signal):
            out = b0 * value + b1 * previous + b2 * previous_2 - a1 * out_1 - a2 * out_2
            output[index] = out
            previous_2, previous = previous, value
            out_2, out_1 = out_1, out
        signal = output
    return np.asarray(signal, dtype=np.float64)


class LoudnessMeter:
    """Accumulate the integrated loudness and the sample peak of a stereo 16-bit stream."""

    def __init__(self, sample_rate: int) -> None:
        if sample_rate % 10:
            raise ValueError("the sample rate must be a multiple of 10 Hz (100 ms hops)")
        self._hop = sample_rate // 10
        self._kernel = _impulse_response(sample_rate)
        self._history = np.zeros((self._kernel.size - 1, 2), dtype=np.float64)
        self._energy_carry = np.zeros(0, dtype=np.float64)
        self._hop_energies: list[np.ndarray] = []
        self._peak = 0

    def feed(self, block: bytes | np.ndarray) -> None:
        """Consume one block of interleaved signed 16-bit little-endian stereo PCM."""
        if isinstance(block, np.ndarray):
            pcm = block.reshape(-1, 2).astype(np.int16, copy=False)
        else:
            pcm = np.frombuffer(block, dtype="<i2").reshape(-1, 2)
        if pcm.shape[0] == 0:
            return
        self._peak = max(self._peak, int(np.abs(pcm.astype(np.int32)).max()))
        weighted = self._k_weight(pcm.astype(np.float64) / _FULL_SCALE)
        self._add_energy(np.square(weighted).sum(axis=1))

    def finish(self) -> LoudnessResult:
        """Return the result for everything fed so far; a partial 100 ms hop is ignored."""
        peak = None if self._peak == 0 else 20.0 * math.log10(self._peak / _FULL_SCALE)
        return LoudnessResult(self._integrated(), peak)

    # ------------------------------------------------------------ filtering

    def _k_weight(self, samples: np.ndarray) -> np.ndarray:
        """Filter a block, continuing from the samples of the previous block."""
        history = self._history.shape[0]
        extended = np.vstack((self._history, samples))
        length = extended.shape[0]
        size = 1 << (length - 1).bit_length()
        spectrum = np.fft.rfft(extended, n=size, axis=0)
        spectrum *= np.fft.rfft(self._kernel, n=size)[:, None]
        filtered = np.fft.irfft(spectrum, n=size, axis=0)[history:length]
        self._history = extended[length - history :].copy()
        return filtered

    def _add_energy(self, energy: np.ndarray) -> None:
        """Sum the channel-weighted energy of each complete 100 ms hop."""
        total = np.concatenate((self._energy_carry, energy)) if self._energy_carry.size else energy
        complete = total.size // self._hop
        if complete:
            self._hop_energies.append(total[: complete * self._hop].reshape(complete, -1).sum(1))
        self._energy_carry = total[complete * self._hop :].copy()

    # --------------------------------------------------------------- gating

    def _integrated(self) -> float | None:
        if not self._hop_energies:
            return None
        hops = np.concatenate(self._hop_energies)
        count = hops.size - (_BLOCK_HOPS - 1)
        if count < 1:
            return None
        block_power = sum(hops[offset : offset + count] for offset in range(_BLOCK_HOPS))
        block_power = block_power / (_BLOCK_HOPS * self._hop)
        with np.errstate(divide="ignore"):
            block_loudness = _OFFSET_DB + 10.0 * np.log10(block_power)
        audible = block_loudness > _ABSOLUTE_GATE_LUFS
        if not audible.any():
            return None
        relative_gate = (
            _OFFSET_DB + 10.0 * math.log10(block_power[audible].mean()) + _RELATIVE_GATE_LU
        )
        gated = audible & (block_loudness > relative_gate)
        return float(_OFFSET_DB + 10.0 * math.log10(block_power[gated].mean()))
