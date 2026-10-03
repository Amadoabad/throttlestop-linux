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


def counter_delta(a0: int, a1: int, width: int = 64) -> int:
    return (a1 - a0) % (1 << width)


def effective_mhz(a0: int, m0: int, a1: int, m1: int, base_mhz: float) -> float:
    """Average frequency from APERF/MPERF deltas.

    MPERF ticks at a fixed reference (TSC/base rate), APERF at the actual
    core rate, so eff = dAPERF/dMPERF * base. This is what exposes clock
    modulation: ratio MHz stays 2800 while effective drops to ~350.
    """
    dm = counter_delta(m0, m1)
    if dm == 0:
        return 0.0
    return counter_delta(a0, a1) / dm * base_mhz


def sample_counters(cpus: list[int]) -> dict[int, tuple[int, int]]:
    return {c: (msr.read_msr(regs.IA32_APERF, c), msr.read_msr(regs.IA32_MPERF, c)) for c in cpus}


def header() -> str:
    return f"{'CPU':>3} {'Ratio':>6} {'Effect':>6} {'C0%':>5} {'Temp':>6} LIMITS"


def format_row(r: dict) -> str:
    t = f"{r['temp']}C" if r["temp"] is not None else "n/a"
    lim = ",".join(r["limits"]) if r["limits"] else "OK"
    eff = f"{r['eff_mhz']:.0f}" if r.get("eff_mhz") is not None else "n/a"
    c0 = f"{r['c0_pct']:.1f}" if r.get("c0_pct") is not None else "n/a"
    return f"{r['cpu']:>3} {r['mhz']:>6} {eff:>6} {c0:>5} {t:>6} {lim}"


def c0_percent(dm: int, dt: float, ref_mhz: float) -> float:
    """Share of the window the core was active (ThrottleStop C0% column)."""
    if dt <= 0 or ref_mhz <= 0:
        return 0.0
    return min(100.0, max(0.0, dm / (ref_mhz * 1e6 * dt) * 100.0))


def run(interval: float = 1.0, count: int = 0) -> int:
    cpus = msr.cpu_list()
    if not cpus:
        print("no /dev/cpu entries found")
        return 1
    base_mhz = cpuinfo.decode_platform_info(msr.read_msr(regs.MSR_PLATFORM_INFO, cpus[0]))[
        "max_non_turbo_ratio"
    ] * 100
    # Clear sticky throttle log bits first (same as ThrottleStop refresh).
    for c in cpus:
        try:
            msr.write_msr(regs.IA32_THERM_STATUS, 0, c)
        except msr.MsrError:
            pass
    i = 0
    try:
        while True:
            c0 = sample_counters(cpus)
            t0 = time.monotonic()
            time.sleep(interval)
            c1 = sample_counters(cpus)
            dt = time.monotonic() - t0
            eff = {c: effective_mhz(c0[c][0], c0[c][1], c1[c][0], c1[c][1], base_mhz) for c in cpus}
            print(header())
            for r in sample_once(cpus):
                r["eff_mhz"] = eff[r["cpu"]]
                r["c0_pct"] = c0_percent(counter_delta(c0[r["cpu"]][1], c1[r["cpu"]][1]), dt, base_mhz)
                print(format_row(r))
            i += 1
            if count and i >= count:
                break
            print()
    except KeyboardInterrupt:
        pass
    return 0
