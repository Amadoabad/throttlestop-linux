"""CPU identity, turbo ratios, thermal decode (Haswell-first)."""
from __future__ import annotations

from . import regs
from .msr import bits


def decode_platform_info(raw: int) -> dict:
    return {
        "max_non_turbo_ratio": bits(raw, 8, 15),
        "max_efficiency_ratio": bits(raw, 40, 47),
        "min_ratio": bits(raw, 48, 55),
    }


def decode_turbo_limit(raw: int) -> dict:
    return {"1c": bits(raw, 0, 7), "2c": bits(raw, 8, 15),
            "3c": bits(raw, 16, 23), "4c": bits(raw, 24, 31)}


def encode_turbo_limit(limits: dict, current: int) -> int:
    out = current
    for shift, key in ((0, "1c"), (8, "2c"), (16, "3c"), (24, "4c")):
        if key in limits and limits[key] is not None:
            v = limits[key]
            if not 8 <= v <= 80:
                raise ValueError(f"turbo {key}={v} out of sane range 8..80")
            out = (out & ~(0xFF << shift)) | ((v & 0xFF) << shift)
    return out & 0xFFFFFFFFFFFFFFFF


def tjmax(raw1a2: int) -> int:
    t = bits(raw1a2, 16, 23)
    return t if t else 100  # Haswell mobile TjMax is 100C; 0 means unread


def trip_temp_c(raw1a2: int) -> int:
    return tjmax(raw1a2) - bits(raw1a2, 24, 29)


def core_temp_c(raw19c: int, tj: int) -> int | None:
    if not bits(raw19c, 31, 31):
        return None
    return tj - bits(raw19c, 16, 22)


def throttle_reasons(raw19c: int) -> list[str]:
    out = []
    if bits(raw19c, 0, 0):
        out.append("THERMAL")
    if bits(raw19c, 2, 2):
        out.append("PROCHOT")
    if bits(raw19c, 10, 10):
        out.append("POWER")
    if bits(raw19c, 12, 12):
        out.append("CURRENT")
    if bits(raw19c, 14, 14):
        out.append("CROSS-DOMAIN")
    return out


def current_ratio(raw198: int) -> int:
    return bits(raw198, 8, 15)
