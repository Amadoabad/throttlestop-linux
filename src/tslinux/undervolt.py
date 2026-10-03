"""Undervolt via MSR 0x150 (OC mailbox). Same wire protocol as ThrottleStop FIVR.

Protocol (from intel-undervolt undervolt.c + throttled throttled.py):
  write: 0x8000001100000000 | (plane << 40) | ((ticks & 0x7FF) << 21)
  read:  write 0x8000001000000000 | (plane << 40), then read back MSR 0x150;
         offset = signed11((value >> 21) & 0x7FF) / 1.024  (mV)

Range is signed 11-bit: 0 down to about -1000 mV. Positive offsets rejected.
"""
from __future__ import annotations

from . import regs

TICKS_PER_MV = 1.024
MIN_TICKS = -(1 << 10)  # -1024
MAX_TICKS = 0
MIN_MV = MIN_TICKS / TICKS_PER_MV  # ~-1000.0


def mv_to_ticks(mv: float) -> int:
    try:
        mv = float(mv)
    except (TypeError, ValueError) as e:
        raise ValueError(f"offset must be a number, got {mv!r}") from e
    if not (MIN_MV <= mv <= 0):
        raise ValueError(f"offset must be {MIN_MV:g}..0 mV, got {mv!r}")
    import math

    if not math.isfinite(mv):
        raise ValueError(f"offset must be finite, got {mv!r}")
    ticks = int(round(mv * TICKS_PER_MV))
    if not MIN_TICKS <= ticks <= MAX_TICKS:
        raise ValueError(f"offset {mv!r} mV does not fit signed 11-bit field")
    return ticks


def encode_write(plane: str, mv: float) -> int:
    if plane not in regs.PLANES:
        raise ValueError(f"unknown plane {plane!r}")
    ticks = mv_to_ticks(mv)
    return 0x8000001100000000 | (regs.PLANES[plane] << 40) | ((ticks & 0x7FF) << 21)


def encode_read(plane: str) -> int:
    if plane not in regs.PLANES:
        raise ValueError(f"unknown plane {plane!r}")
    return 0x8000001000000000 | (regs.PLANES[plane] << 40)


def decode_mv(raw: int) -> int:
    field = (raw >> 21) & 0x7FF
    signed = field if field < 0x400 else field - 0x800
    return int(round(signed / TICKS_PER_MV))


# IccMax shares the 0x150 mailbox: read-select command 0x16, write 0x17,
# 10-bit quarter-ampere field (throttled.py, FIVR IccMax slider).
ICCMAX_PLANES = {"core": 0, "gpu": 1, "cache": 2}
ICCMAX_STEPS_PER_A = 4
ICCMAX_MAX_FIELD = 0x3FF


def iccmax_to_field(amps: float) -> int:
    try:
        amps = float(amps)
    except (TypeError, ValueError) as e:
        raise ValueError(f"IccMax must be a number, got {amps!r}") from e
    import math

    max_a = ICCMAX_MAX_FIELD / ICCMAX_STEPS_PER_A
    if not math.isfinite(amps) or not 0 < amps <= max_a:
        raise ValueError(f"IccMax must be 0..{max_a:g} A, got {amps!r}")
    field = int(amps * ICCMAX_STEPS_PER_A)  # floor: never enforce above asked
    if not 1 <= field <= ICCMAX_MAX_FIELD:
        raise ValueError(f"IccMax {amps!r} A quantises outside the 10-bit field")
    return field


def iccmax_encode_write(plane: str, amps: float) -> int:
    if plane not in ICCMAX_PLANES:
        raise ValueError(f"unknown current plane {plane!r}")
    return 0x8000001700000000 | (ICCMAX_PLANES[plane] << 40) | iccmax_to_field(amps)


def iccmax_encode_read(plane: str) -> int:
    if plane not in ICCMAX_PLANES:
        raise ValueError(f"unknown current plane {plane!r}")
    return 0x8000001600000000 | (ICCMAX_PLANES[plane] << 40)


def iccmax_decode_amp(raw: int) -> float:
    return (raw & 0x3FF) / 4.0
