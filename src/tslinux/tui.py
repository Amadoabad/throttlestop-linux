"""Terminal TUI: live ThrottleStop-style dashboard (Textual).

Run as root: sudo tslinux tui
Keys: a = apply config, r = reset to snapshot, q = quit.
"""
from __future__ import annotations

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import DataTable, Footer, Header, RichLog

from . import config, cpu as cpuinfo, controls, engine, monitor, msr, power, regs, undervolt


def package_line() -> str:
    cpus = msr.cpu_list()
    c0 = cpus[0]
    raw606 = msr.read_msr(regs.MSR_RAPL_POWER_UNIT, c0)
    d = power.decode(msr.read_msr(regs.MSR_PKG_POWER_LIMIT, c0))
    pu, tu = power.power_unit(raw606), power.time_unit(raw606)
    turbo = cpuinfo.decode_turbo_limit(msr.read_msr(regs.MSR_TURBO_RATIO_LIMIT, c0))
    r1a0 = msr.read_msr(regs.IA32_MISC_ENABLE, c0)
    r1fc = msr.read_msr(regs.MSR_POWER_CTL, c0)
    r19a = msr.read_msr(regs.IA32_CLOCK_MODULATION, c0)
    r1a2 = msr.read_msr(regs.MSR_TEMPERATURE_TARGET, c0)
    tl = "/".join(str(turbo[k]) for k in ("1c", "2c", "3c", "4c"))
    return (
        f"PL1 {d['pl1_w_ticks']*pu:.0f}W/{power.field_to_seconds(d['pl1_window'], tu):.2f}s "
        f"PL2 {d['pl2_w_ticks']*pu:.0f}W  turbo {tl} "
        f"{'NOTURBO' if controls.turbo_disabled(r1a0) else 'turbo'} "
        f"{'noBD' if controls.bdprochot_disabled(r1fc) else 'BD'} "
        f"clk {controls.clockmod_percent(r19a):.0f}% trip {cpuinfo.trip_temp_c(r1a2)}C"
        + (" LOCK" if d["locked"] else "")
    )


def undervolt_line() -> str:
    c0 = msr.cpu_list()[0]
    parts = []
    for p in regs.PLANE_NAMES:
        msr.write_msr(regs.MSR_OC_MAILBOX, undervolt.encode_read(p), c0)
        raw = msr.read_msr(regs.MSR_OC_MAILBOX, c0) & 0xFFFFFFFF
        parts.append(f"{p} {undervolt.decode_mv(raw)}mV")
    return "  ".join(parts)


class TsApp(App):
    TITLE = "ThrottleStop Linux"
    BINDINGS = [
        Binding("a", "apply", "Apply config"),
        Binding("r", "reset", "Reset"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, interval: float = 1.0):
        super().__init__()
        self.tick_interval = interval
        self.base_mhz = 2800.0
        self.prev: dict[int, tuple[int, int]] | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            yield DataTable(id="cores")
            yield RichLog(id="log", max_lines=100)
        yield Footer()

    def on_mount(self) -> None:
        engine.require_root()
        table = self.query_one("#cores", DataTable)
        table.add_column("CPU", width=4, key="cpu")
        table.add_column("Ratio", width=7, key="ratio")
        table.add_column("Effect", width=8, key="eff")
        table.add_column("Temp", width=7, key="temp")
        table.add_column("Limits", width=16, key="lim")
        cpus = msr.cpu_list()
        self.base_mhz = (
            cpuinfo.decode_platform_info(msr.read_msr(regs.MSR_PLATFORM_INFO, cpus[0]))[
                "max_non_turbo_ratio"
            ] * 100
        )
        for c in cpus:
            table.add_row(str(c), "-", "-", "-", "-", key=str(c))
        self.say(package_line())
        self.say(undervolt_line())
        self.set_interval(self.tick_interval, self.refresh_rows)

    def say(self, msg: str) -> None:
        self.query_one("#log", RichLog).write(msg)

    def refresh_rows(self) -> None:
        try:
            cpus = msr.cpu_list()
            cur = monitor.sample_counters(cpus)
            eff = {}
            if self.prev is not None:
                for c in cpus:
                    a0, m0 = self.prev[c]
                    a1, m1 = cur[c]
                    eff[c] = monitor.effective_mhz(a0, m0, a1, m1, self.base_mhz)
            self.prev = cur
            table = self.query_one("#cores", DataTable)
            for r in monitor.sample_once(cpus):
                e = f"{eff[r['cpu']]:.0f}" if r["cpu"] in eff else "-"
                t = f"{r['temp']}C" if r["temp"] is not None else "n/a"
                lim = ",".join(r["limits"]) if r["limits"] else "OK"
                table.update_cell(str(r["cpu"]), "ratio", str(r["mhz"]))
                table.update_cell(str(r["cpu"]), "eff", e)
                table.update_cell(str(r["cpu"]), "temp", t)
                table.update_cell(str(r["cpu"]), "lim", lim)
            self.sub_title = package_line()
        except msr.MsrError as e:
            self.say(f"MSR error: {e}")

    def action_apply(self) -> None:
        import os

        try:
            cfg = config.load_config()
            if not os.path.exists(config.SNAPSHOT_PATH):
                config.save_snapshot(engine.capture_defaults())
                self.say(f"saved defaults -> {config.SNAPSHOT_PATH}")
            for line in engine.apply_all(cfg):
                self.say(line)
        except Exception as e:  # noqa: BLE001 - show in TUI
            self.say(f"apply failed: {e}")

    def action_reset(self) -> None:
        try:
            for line in engine.reset_from_snapshot():
                self.say(line)
        except Exception as e:  # noqa: BLE001
            self.say(f"reset failed: {e}")


def run_tui(interval: float = 1.0) -> int:
    engine.require_root()
    TsApp(interval).run()
    return 0
