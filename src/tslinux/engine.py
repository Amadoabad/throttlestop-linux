"""Apply / reset engine. Every write mirrors a ThrottleStop action."""
from __future__ import annotations

import os

from . import config, controls, cpu as cpuinfo, msr, power, regs, undervolt

NEED_ROOT = "must run as root (e.g. sudo tslinux ...)"


def require_root() -> None:
    if os.geteuid() != 0:
        raise SystemExit(f"error: {NEED_ROOT}")


def capture_defaults() -> dict:
    cpus = msr.cpu_list()
    c0 = cpus[0]
    planes = {}
    for p in regs.PLANE_NAMES:
        msr.write_msr(regs.MSR_OC_MAILBOX, undervolt.encode_read(p), c0)
        planes[p] = msr.read_msr(regs.MSR_OC_MAILBOX, c0) & 0xFFFFFFFF
    return {
        "oc_mailbox": planes,
        "pkg_power_limit": msr.read_msr(regs.MSR_PKG_POWER_LIMIT, c0),
        "turbo_ratio_limit": msr.read_msr(regs.MSR_TURBO_RATIO_LIMIT, c0),
        "misc_enable": [msr.read_msr(regs.IA32_MISC_ENABLE, c) for c in cpus],
        "power_ctl": [msr.read_msr(regs.MSR_POWER_CTL, c) for c in cpus],
        "clock_mod": [msr.read_msr(regs.IA32_CLOCK_MODULATION, c) for c in cpus],
        "temp_target": msr.read_msr(regs.MSR_TEMPERATURE_TARGET, c0),
        "cpus": cpus,
    }


def apply_undervolts(offsets: dict, dry_run: bool = False) -> list[str]:
    cpus = msr.cpu_list()
    log = []
    for plane, mv in offsets.items():
        if float(mv) == 0.0:
            continue
        val = undervolt.encode_write(plane, float(mv))
        log.append(f"plane {plane}: {mv} mV -> {val:#x}")
        if not dry_run:
            for c in cpus:
                msr.write_msr(regs.MSR_OC_MAILBOX, val, c)
    return log


def apply_power(pl1_w, pl1_s, pl2_w, pl2_s, dry_run: bool = False) -> str:
    if all(v is None for v in (pl1_w, pl1_s, pl2_w, pl2_s)):
        return "power: unchanged (no config)"
    c0 = msr.cpu_list()[0]
    raw606 = msr.read_msr(regs.MSR_RAPL_POWER_UNIT, c0)
    cur = power.decode(msr.read_msr(regs.MSR_PKG_POWER_LIMIT, c0))
    pu, tu = power.power_unit(raw606), power.time_unit(raw606)
    pl1 = cur["pl1_w_ticks"] if pl1_w is None else int(round(float(pl1_w) / pu))
    pl2 = cur["pl2_w_ticks"] if pl2_w is None else int(round(float(pl2_w) / pu))
    tw1 = cur["pl1_window"] if pl1_s is None else power.yz_to_field(*power.time_window_to_yz(float(pl1_s), tu))
    tw2 = cur["pl2_window"] if pl2_s is None else power.yz_to_field(*power.time_window_to_yz(float(pl2_s), tu))
    val = power.encode(pl1, tw1, pl2, tw2)
    if not dry_run:
        msr.write_msr(regs.MSR_PKG_POWER_LIMIT, val, c0)
    return f"power: PL1={pl1_w}W PL2={pl2_w}W -> {val:#x}"


def apply_all(cfg: dict, dry_run: bool = False) -> list[str]:
    log: list[str] = []
    log += apply_undervolts(cfg["undervolt"], dry_run)
    log.append(apply_power(cfg["power"]["pl1_w"], cfg["power"]["pl1_s"],
                           cfg["power"]["pl2_w"], cfg["power"]["pl2_s"], dry_run))
    cpus = msr.cpu_list()
    # Turbo disable/enable (ThrottleStop main panel)
    for c in cpus:
        cur = msr.read_msr(regs.IA32_MISC_ENABLE, c)
        new = controls.set_turbo(cur, bool(cfg["turbo"]["disable"]))
        if new != cur and not dry_run:
            msr.write_msr(regs.IA32_MISC_ENABLE, new, c)
    log.append(f"turbo: {'disabled' if cfg['turbo']['disable'] else 'enabled'}")
    # Turbo ratio limits
    if cfg["turbo"]["limits"]:
        c0 = cpus[0]
        cur = msr.read_msr(regs.MSR_TURBO_RATIO_LIMIT, c0)
        new = cpuinfo.encode_turbo_limit(cfg["turbo"]["limits"], cur)
        if not dry_run:
            msr.write_msr(regs.MSR_TURBO_RATIO_LIMIT, new, c0)
        log.append(f"turbo limits: {cfg['turbo']['limits']}")
    # BD PROCHOT
    for c in cpus:
        cur = msr.read_msr(regs.MSR_POWER_CTL, c)
        new = controls.set_bdprochot(cur, bool(cfg["bdprochot_disable"]))
        if new != cur and not dry_run:
            msr.write_msr(regs.MSR_POWER_CTL, new, c)
    log.append(f"bdprochot: {'disabled' if cfg['bdprochot_disable'] else 'enabled'}")
    # Clock modulation -> 100%
    if cfg.get("clockmod_full"):
        for c in cpus:
            cur = msr.read_msr(regs.IA32_CLOCK_MODULATION, c)
            new = controls.clockmod_full(cur)
            if new != cur and not dry_run:
                msr.write_msr(regs.IA32_CLOCK_MODULATION, new, c)
        log.append("clockmod: forced 100%")
    # Temperature trip point
    if cfg.get("trip_temp_c") is not None:
        c0 = cpus[0]
        cur = msr.read_msr(regs.MSR_TEMPERATURE_TARGET, c0)
        new = controls.set_trip_offset(cur, int(cfg["trip_temp_c"]))
        if not dry_run:
            msr.write_msr(regs.MSR_TEMPERATURE_TARGET, new, c0)
        log.append(f"trip: {cfg['trip_temp_c']}C")
    return log


def reset_from_snapshot(dry_run: bool = False) -> list[str]:
    snap = config.load_snapshot()
    log: list[str] = []
    cpus = snap["cpus"]
    # Undervolt planes back to captured raw values (normally 0 mV)
    for p, raw in snap["oc_mailbox"].items():
        mv = undervolt.decode_mv(raw)
        val = undervolt.encode_write(p, float(mv))
        log.append(f"reset {p}: {mv} mV")
        if not dry_run:
            for c in cpus:
                msr.write_msr(regs.MSR_OC_MAILBOX, val, c)
    c0 = cpus[0]
    if not dry_run:
        msr.write_msr(regs.MSR_PKG_POWER_LIMIT, snap["pkg_power_limit"], c0)
        msr.write_msr(regs.MSR_TURBO_RATIO_LIMIT, snap["turbo_ratio_limit"], c0)
        msr.write_msr(regs.MSR_TEMPERATURE_TARGET, snap["temp_target"], c0)
        for c, v in zip(cpus, snap["misc_enable"]):
            msr.write_msr(regs.IA32_MISC_ENABLE, v, c)
        for c, v in zip(cpus, snap["power_ctl"]):
            msr.write_msr(regs.MSR_POWER_CTL, v, c)
        for c, v in zip(cpus, snap["clock_mod"]):
            msr.write_msr(regs.IA32_CLOCK_MODULATION, v, c)
        # Clear sticky throttle logs so monitor starts clean
        for c in cpus:
            try:
                msr.write_msr(regs.IA32_THERM_STATUS, 0, c)
            except msr.MsrError:
                pass
    log.append("power/turbo/bdprochot/clockmod/temp restored from snapshot")
    return log
