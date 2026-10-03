"""Terminal TUI: live ThrottleStop-style dashboard + control panel (Textual).

Run as root: sudo tslinux tui
Keys: a = apply panel values, s = save panel to /etc/tslinux.conf,
      r = reset to snapshot, q = quit.
"""
from __future__ import annotations

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Checkbox, DataTable, Footer, Header, Input, RichLog

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


def read_live_undervolts() -> dict[str, float]:
    c0 = msr.cpu_list()[0]
    out = {}
    for p in regs.PLANE_NAMES:
        msr.write_msr(regs.MSR_OC_MAILBOX, undervolt.encode_read(p), c0)
        raw = msr.read_msr(regs.MSR_OC_MAILBOX, c0) & 0xFFFFFFFF
        out[p] = float(undervolt.decode_mv(raw))
    return out


def read_live_power() -> dict:
    c0 = msr.cpu_list()[0]
    raw606 = msr.read_msr(regs.MSR_RAPL_POWER_UNIT, c0)
    d = power.decode(msr.read_msr(regs.MSR_PKG_POWER_LIMIT, c0))
    pu, tu = power.power_unit(raw606), power.time_unit(raw606)
    return {
        "pl1_w": round(d["pl1_w_ticks"] * pu, 1),
        "pl1_s": round(power.field_to_seconds(d["pl1_window"], tu), 3),
        "pl2_w": round(d["pl2_w_ticks"] * pu, 1),
        "pl2_s": round(power.field_to_seconds(d["pl2_window"], tu), 4),
    }


def parse_float(text: str) -> float | None:
    text = text.strip()
    if not text:
        return None
    return float(text)


class TsApp(App):
    TITLE = "ThrottleStop Linux"
    BINDINGS = [
        Binding("a", "apply", "Apply"),
        Binding("s", "save", "Save"),
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
            with Vertical(id="side"):
                yield RichLog(id="log", max_lines=100)
                with Horizontal(id="uvrow"):
                    for p in regs.PLANE_NAMES:
                        yield Input(placeholder=f"{p} mV", id=f"uv-{p}")
                with Horizontal(id="plrow"):
                    for key in ("pl1_w", "pl2_w", "trip"):
                        yield Input(placeholder=key, id=f"in-{key}")
                with Horizontal(id="flags"):
                    yield Checkbox("Disable Turbo", id="ck-turbo")
                    yield Checkbox("BDPROCHOT off", id="ck-bd")
                with Horizontal(id="btns"):
                    yield Button("Apply", id="btn-apply", variant="primary")
                    yield Button("Save", id="btn-save")
                    yield Button("Reset", id="btn-reset")
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
        self.prefill()
        self.set_interval(self.tick_interval, self.refresh_rows)

    def say(self, msg: str) -> None:
        self.query_one("#log", RichLog).write(msg)

    def prefill(self) -> None:
        """Fill inputs from live hardware (not the config file)."""
        c0 = msr.cpu_list()[0]
        for p, mv in read_live_undervolts().items():
            self.query_one(f"#uv-{p}", Input).value = str(mv)
        live = read_live_power()
        self.query_one("#in-pl1_w", Input).value = str(live["pl1_w"])
        self.query_one("#in-pl2_w", Input).value = str(live["pl2_w"])
        r1a2 = msr.read_msr(regs.MSR_TEMPERATURE_TARGET, c0)
        self.query_one("#in-trip", Input).value = str(cpuinfo.trip_temp_c(r1a2))
        r1a0 = msr.read_msr(regs.IA32_MISC_ENABLE, c0)
        r1fc = msr.read_msr(regs.MSR_POWER_CTL, c0)
        self.query_one("#ck-turbo", Checkbox).value = controls.turbo_disabled(r1a0)
        self.query_one("#ck-bd", Checkbox).value = controls.bdprochot_disabled(r1fc)

    def panel_config(self) -> dict:
        uvs = {}
        for p in regs.PLANE_NAMES:
            v = parse_float(self.query_one(f"#uv-{p}", Input).value)
            uvs[p] = v if v is not None else 0.0
        trip = parse_float(self.query_one("#in-trip", Input).value)
        return {
            "undervolt": uvs,
            "power": {
                "pl1_w": parse_float(self.query_one("#in-pl1_w", Input).value),
                "pl1_s": None,
                "pl2_w": parse_float(self.query_one("#in-pl2_w", Input).value),
                "pl2_s": None,
            },
            "turbo": {"disable": self.query_one("#ck-turbo", Checkbox).value, "limits": {}},
            "bdprochot_disable": self.query_one("#ck-bd", Checkbox).value,
            "trip_temp_c": int(trip) if trip is not None else None,
            "clockmod_full": True,
        }

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

    def do_apply(self) -> None:
        import os

        try:
            cfg = self.panel_config()
            if not os.path.exists(config.SNAPSHOT_PATH):
                config.save_snapshot(engine.capture_defaults())
                self.say(f"saved defaults -> {config.SNAPSHOT_PATH}")
            for line in engine.apply_all(cfg):
                self.say(line)
        except Exception as e:  # noqa: BLE001 - show in TUI
            self.say(f"apply failed: {e}")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-apply":
            self.do_apply()
        elif event.button.id == "btn-save":
            try:
                config.save_config(self.panel_config())
                self.say(f"saved -> {config.CONFIG_PATH}")
            except Exception as e:  # noqa: BLE001
                self.say(f"save failed: {e}")
        elif event.button.id == "btn-reset":
            self.action_reset()

    def action_apply(self) -> None:
        self.do_apply()

    def action_save(self) -> None:
        try:
            config.save_config(self.panel_config())
            self.say(f"saved -> {config.CONFIG_PATH}")
        except Exception as e:  # noqa: BLE001
            self.say(f"save failed: {e}")

    def action_reset(self) -> None:
        try:
            for line in engine.reset_from_snapshot():
                self.say(line)
            self.prefill()
        except Exception as e:  # noqa: BLE001
            self.say(f"reset failed: {e}")


def run_tui(interval: float = 1.0) -> int:
    engine.require_root()
    TsApp(interval).run()
    return 0
