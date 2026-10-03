"""High-level controls: turbo, BD PROCHOT, clock modulation, temp target.

Each mirrors one ThrottleStop checkbox, using the same MSR bit.
All writes are read-modify-write and never set lock bits.
"""
from __future__ import annotations

from . import regs
from .msr import bits


def turbo_disabled(raw1a0: int) -> bool:
    return bool((raw1a0 >> regs.MISC_ENABLE_TURBO_DISABLE_BIT) & 1)


def set_turbo(raw1a0: int, disable: bool) -> int:
    if disable:
        return raw1a0 | (1 << regs.MISC_ENABLE_TURBO_DISABLE_BIT)
    return raw1a0 & ~(1 << regs.MISC_ENABLE_TURBO_DISABLE_BIT)


def bdprochot_disabled(raw1fc: int) -> bool:
    return bits(raw1fc, 0, 0) == 0


def set_bdprochot(raw1fc: int, disable: bool) -> int:
    if disable:
        return raw1fc & ~1  # clear bit 0, per throttled set_disable_bdprochot
    return raw1fc | 1


def clockmod_percent(raw19a: int) -> float:
    if bits(raw19a, 4, 4) == 0:
        return 100.0
    duty = bits(raw19a, 1, 3)
    # On-demand modulation: 0b000 reserved -> treat as 100, else 12.5% steps
    table = {1: 12.5, 2: 25.0, 3: 37.5, 4: 50.0, 5: 62.5, 6: 75.0, 7: 87.5}
    return table.get(duty, 100.0)


def clockmod_full(raw19a: int) -> int:
    """Force 100% (ThrottleStop 'Clock Mod' fix): clear enable bit."""
    return raw19a & ~(1 << 4)


def set_trip_offset(raw1a2: int, trip_c: int) -> int:
    tj = bits(raw1a2, 16, 23) or 100
    offset = tj - trip_c
    if not 0 <= offset <= 63:
        raise ValueError(f"trip {trip_c}C needs 6-bit offset 0..63 (tj={tj})")
    return (raw1a2 & 0xFFFFFFC0FFFFFF) | ((offset & 0x3F) << 24)
