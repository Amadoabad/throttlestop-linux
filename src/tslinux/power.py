"""Package power limits, MSR 0x610. Same fields ThrottleStop TPL edits.

Layout: PL1 power [14:0], PL1 enable [15], PL1 window [23:17],
        PL2 power [46:32], PL2 enable [47], PL2 window [55:49].
Bit 63 is a lock bit: this tool never sets it, so reboot always resets.
Units come from MSR 0x606: watts = 1/2^[3:0], seconds = 1/2^[19:16].
"""
from __future__ import annotations

POWER_MASK = (1 << 15) - 1
WINDOW_MASK = (1 << 7) - 1


def power_unit(raw606: int) -> float:
    return 1.0 / 2 ** (raw606 & 0xF)


def time_unit(raw606: int) -> float:
    return 1.0 / 2 ** ((raw606 >> 16) & 0xF)


def decode(raw610: int) -> dict:
    from .msr import bits

    return {
        "pl1_w_ticks": bits(raw610, 0, 14),
        "pl1_enable": bits(raw610, 15, 15),
        "pl1_window": bits(raw610, 17, 23),
        "pl2_w_ticks": bits(raw610, 32, 46),
        "pl2_enable": bits(raw610, 47, 47),
        "pl2_window": bits(raw610, 49, 55),
        "locked": bits(raw610, 63, 63),
    }


def encode(pl1: int, tw1: int, pl2: int, tw2: int) -> int:
    for name, val, mask in (("pl1", pl1, POWER_MASK), ("tw1", tw1, WINDOW_MASK),
                            ("pl2", pl2, POWER_MASK), ("tw2", tw2, WINDOW_MASK)):
        if not isinstance(val, int) or not 0 <= val <= mask:
            raise ValueError(f"{name}={val!r} does not fit {mask.bit_length()}-bit field")
    if pl1 == 0 or pl2 == 0:
        raise ValueError("PL1/PL2 power must be >= 1 tick (0 would mean 0 W)")
    return pl1 | (1 << 15) | (1 << 16) | (tw1 << 17) | (pl2 << 32) | (1 << 47) | (tw2 << 49)


def time_window_to_yz(seconds: float, tunit: float) -> tuple[int, int]:
    for y in range(32):
        for z in range(4):
            if seconds <= (2 ** y) * (1.0 + z / 4.0) * tunit:
                return (y, z)
    raise ValueError("time window too large")


def yz_to_field(y: int, z: int) -> int:
    return (y & 0x1F) | ((z & 0x3) << 5)


def field_to_seconds(field: int, tunit: float) -> float:
    y, z = field & 0x1F, (field >> 5) & 0x3
    return (2 ** y) * (1.0 + z / 4.0) * tunit
