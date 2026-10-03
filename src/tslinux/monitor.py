"""Live monitor: ThrottleStop right-panel parity (text mode)."""
from __future__ import annotations

import time

from . import cpu as cpuinfo
from . import msr, power, regs


def sample_once(cpus: list[int]) -> list[dict]:
    tj = cpuinfo.tjmax(msr.read_msr(regs.MSR_TEMPERATURE_TARGET, cpus[0]))
    rows = []
    for c in cpus:
        raw_status = msr.read_msr(regs.IA32_PERF_STATUS, c)
        raw_th = msr.read_msr(regs.IA32_THERM_STATUS, c)
        rows.append({
            "cpu": c,
            "ratio": cpuinfo.current_ratio(raw_status),
            "mhz": cpuinfo.current_ratio(raw_status) * 100,
            "temp": cpuinfo.core_temp_c(raw_th, tj),
            "limits": cpuinfo.throttle_reasons(raw_th),
        })
    return rows


def pkg_watts(prev_e: int, cur_e: int, dt: float, raw606: int) -> float:
    eunit = 1.0 / 2 ** ((raw606 >> 8) & 0x1F)
    return (cur_e - prev_e) * eunit / dt if dt > 0 else 0.0


def header() -> str:
    return f"{'CPU':>3} {'MHz':>6} {'Temp':>6} LIMITS"


def format_row(r: dict) -> str:
    t = f"{r['temp']}C" if r["temp"] is not None else "n/a"
    lim = ",".join(r["limits"]) if r["limits"] else "OK"
    return f"{r['cpu']:>3} {r['mhz']:>6} {t:>6} {lim}"


def run(interval: float = 1.0, count: int = 0) -> int:
    cpus = msr.cpu_list()
    if not cpus:
        print("no /dev/cpu entries found")
        return 1
    # Clear sticky throttle log bits first (same as ThrottleStop refresh).
    for c in cpus:
        try:
            msr.write_msr(regs.IA32_THERM_STATUS, 0, c)
        except msr.MsrError:
            pass
    i = 0
    try:
        while True:
            print(header())
            for r in sample_once(cpus):
                print(format_row(r))
            i += 1
            if count and i >= count:
                break
            time.sleep(interval)
            print()
    except KeyboardInterrupt:
        pass
    return 0
