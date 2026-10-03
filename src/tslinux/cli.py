"""tslinux CLI: status / apply / monitor / reset / daemon."""
from __future__ import annotations

import argparse
import os
import time

from . import config, cpu as cpuinfo, controls, engine, monitor, msr, power, regs, undervolt


def cmd_status(_a) -> int:
    engine.require_root()
    try:
        cpus = msr.cpu_list()
        c0 = cpus[0]
        plat = cpuinfo.decode_platform_info(msr.read_msr(regs.MSR_PLATFORM_INFO, c0))
        print(f"cpus: {len(cpus)}  base ratio: {plat['max_non_turbo_ratio']}  min: {plat['min_ratio']}")
        print(f"turbo limits: {cpuinfo.decode_turbo_limit(msr.read_msr(regs.MSR_TURBO_RATIO_LIMIT, c0))}")
        raw606 = msr.read_msr(regs.MSR_RAPL_POWER_UNIT, c0)
        raw610 = msr.read_msr(regs.MSR_PKG_POWER_LIMIT, c0)
        d = power.decode(raw610)
        pu, tu = power.power_unit(raw606), power.time_unit(raw606)
        print(f"power: PL1={d['pl1_w_ticks']*pu:.1f}W win={power.field_to_seconds(d['pl1_window'], tu):.3f}s "
              f"PL2={d['pl2_w_ticks']*pu:.1f}W win={power.field_to_seconds(d['pl2_window'], tu):.3f}s "
              f"locked={d['locked']}")
        for p in regs.PLANE_NAMES:
            msr.write_msr(regs.MSR_OC_MAILBOX, undervolt.encode_read(p), c0)
            raw = msr.read_msr(regs.MSR_OC_MAILBOX, c0) & 0xFFFFFFFF
            print(f"undervolt {p}: {undervolt.decode_mv(raw)} mV")
        r1a0 = msr.read_msr(regs.IA32_MISC_ENABLE, c0)
        r1fc = msr.read_msr(regs.MSR_POWER_CTL, c0)
        r19a = msr.read_msr(regs.IA32_CLOCK_MODULATION, c0)
        r1a2 = msr.read_msr(regs.MSR_TEMPERATURE_TARGET, c0)
        print(f"turbo: {'disabled' if controls.turbo_disabled(r1a0) else 'enabled'}  "
              f"bdprochot: {'disabled' if controls.bdprochot_disabled(r1fc) else 'enabled'}  "
              f"clockmod: {controls.clockmod_percent(r19a):.1f}% (raw {r19a:#x})  "
              f"trip: {cpuinfo.trip_temp_c(r1a2)}C")
    except (msr.MsrError, IndexError) as e:
        print(f"cannot access MSRs: {e}")
        return 1
    return 0


def cmd_apply(a) -> int:
    engine.require_root()
    cfg = config.load_config(a.config)
    if not os.path.exists(config.SNAPSHOT_PATH) and not a.dry_run:
        config.save_snapshot(engine.capture_defaults())
        print(f"saved defaults -> {config.SNAPSHOT_PATH}")
    for line in engine.apply_all(cfg, dry_run=a.dry_run):
        print(("[dry-run] " if a.dry_run else "") + line)
    return 0


def cmd_reset(a) -> int:
    engine.require_root()
    for line in engine.reset_from_snapshot(dry_run=a.dry_run):
        print(("[dry-run] " if a.dry_run else "") + line)
    print("note: reboot also resets everything (MSRs are volatile, no lock bits set)")
    return 0


def cmd_monitor(a) -> int:
    engine.require_root()
    return monitor.run(interval=a.interval, count=a.count)


def cmd_daemon(a) -> int:
    engine.require_root()
    cfg = config.load_config(a.config)
    print(f"daemon: re-applying every {a.interval}s (Ctrl+C to stop; EC resets fought same as ThrottleStop)")
    try:
        while True:
            for line in engine.apply_all(cfg):
                print(line, flush=True)
            time.sleep(a.interval)
    except KeyboardInterrupt:
        pass
    return 0


def build() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="tslinux", description="Native Linux ThrottleStop mechanisms")
    p.add_argument("--config", default=config.CONFIG_PATH)
    sub = p.add_subparsers(dest="cmd", required=True)
    ps = sub.add_parser("status", help="show current MSR state")
    ps.set_defaults(fn=cmd_status)
    pa = sub.add_parser("apply", help="apply config file")
    pa.set_defaults(fn=cmd_apply)
    pa.add_argument("--dry-run", action="store_true")
    pr = sub.add_parser("reset", help="restore snapshot (no reboot needed)")
    pr.set_defaults(fn=cmd_reset)
    pr.add_argument("--dry-run", action="store_true")
    pm = sub.add_parser("monitor", help="live freq/temp/limit monitor")
    pm.set_defaults(fn=cmd_monitor)
    pm.add_argument("--interval", type=float, default=1.0)
    pm.add_argument("--count", type=int, default=0)
    pd = sub.add_parser("daemon", help="re-apply loop against EC resets")
    pd.set_defaults(fn=cmd_daemon)
    pd.add_argument("--interval", type=float, default=5.0)
    pg = sub.add_parser("gui", help="ThrottleStop-like window (Tkinter, root)")
    pg.set_defaults(fn=cmd_gui)
    return p


def cmd_gui(_a) -> int:
    engine.require_root()
    from .gui import run_gui

    run_gui()
    return 0


def main() -> int:
    a = build().parse_args()
    return a.fn(a)
