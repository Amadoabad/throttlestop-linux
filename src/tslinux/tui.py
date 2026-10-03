"""Terminal TUI: ThrottleStop-style dashboard + control panel (Textual).

Run as root: sudo tslinux tui
Keys: 1-4 profiles, a apply panel, s save panel to file, r reset, q quit.
"""
from __future__ import annotations

import time

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


def parse_int(text: str) -> int | None:
    text = text.strip()
    if not text:
        return None
    return int(float(text))


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
        self.prev_t = 0.0
        self.profile = 1
        self.file_cfg: dict = {}

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            yield DataTable(id="cores")
            with Vertical(id="side"):
                yield RichLog(id="log", max_lines=100)
                with Horizontal(id="uvrow"):
                    for p in regs.PLANE_NAMES:
                        yield Input(placeholder=f"{p} mV", id=f"uv-{p}")
                with Horizontal(id="icrow"):
                    for p in ("core", "cache"):
                        yield Input(placeholder=f"icc {p} A", id=f"icc-{p}")
                    yield Input(placeholder="multi x", id="in-multi")
                    yield Input(placeholder="trip C", id="in-trip")
                with Horizontal(id="plrow"):
                    for key in ("pl1_w", "pl1_s", "pl2_w", "pl2_s"):
                        yield Input(placeholder=key, id=f"in-{key}")
                with Horizontal(id="trow"):
                    for key in ("1c", "2c", "3c", "4c"):
                        yield Input(placeholder=f"turbo {key}", id=f"tb-{key}")
                with Horizontal(id="flags"):
                    yield Checkbox("Disable Turbo", id="ck-turbo")
                    yield Checkbox("SpeedStep", id="ck-eist")
                    yield Checkbox("BDPROCHOT off", id="ck-bd")
                with Horizontal(id="btns"):
                    yield Button("Apply", id="btn-apply", variant="primary")
                    yield Button("Save P1-4", id="btn-save")
                    yield Button("Reset", id="btn-reset")
        yield Footer()

    def on_mount(self) -> None:
        engine.require_root()
        table = self.query_one("#cores", DataTable)
        table.add_column("CPU", width=4, key="cpu")
        table.add_column("Ratio", width=7, key="ratio")
        table.add_column("Effect", width=8, key="eff")
        table.add_column("C0%", width=6, key="c0")
        table.add_column("Mod", width=6, key="mod")
        table.add_column("Temp", width=7, key="temp")
        table.add_column("Limits", width=16, key="lim")
        cpus = msr.cpu_list()
        self.base_mhz = (
            cpuinfo.decode_platform_info(msr.read_msr(regs.MSR_PLATFORM_INFO, cpus[0]))[
                "max_non_turbo_ratio"
            ] * 100
        )
        for c in cpus:
            table.add_row(str(c), "-", "-", "-", "-", "-", "-", key=str(c))
        try:
            self.file_cfg = config.load_config()
        except Exception as e:  # noqa: BLE001
            self.say(f"config: {e}")
        self.say(package_line())
        self.fill_hardware()
        self.set_interval(self.tick_interval, self.refresh_rows)

    def say(self, msg: str) -> None:
        self.query_one("#log", RichLog).write(msg)

    def _set(self, wid: str, val) -> None:
        self.query_one(f"#{wid}", Input).value = "" if val is None else str(val)

    def fill_hardware(self) -> None:
        """Fill panel from live hardware (power-on truth)."""
        c0 = msr.cpu_list()[0]
        for p, mv in read_live_undervolts().items():
            self._set(f"uv-{p}", mv)
        for p, a in engine.read_live_iccmax().items():
            if p in ("core", "cache"):
                self._set(f"icc-{p}", round(a, 2))
        live = read_live_power()
        for key in ("pl1_w", "pl1_s", "pl2_w", "pl2_s"):
            self._set(f"in-{key}", live[key])
        r1a2 = msr.read_msr(regs.MSR_TEMPERATURE_TARGET, c0)
        self._set("in-trip", cpuinfo.trip_temp_c(r1a2))
        self._set("in-multi", controls.perf_target_ratio(msr.read_msr(regs.IA32_PERF_CTL, c0)))
        tl = cpuinfo.decode_turbo_limit(msr.read_msr(regs.MSR_TURBO_RATIO_LIMIT, c0))
        for key in ("1c", "2c", "3c", "4c"):
            self._set(f"tb-{key}", tl[key])
        r1a0 = msr.read_msr(regs.IA32_MISC_ENABLE, c0)
        r1fc = msr.read_msr(regs.MSR_POWER_CTL, c0)
        self.query_one("#ck-turbo", Checkbox).value = controls.turbo_disabled(r1a0)
        self.query_one("#ck-eist", Checkbox).value = controls.eist_enabled(r1a0)
        self.query_one("#ck-bd", Checkbox).value = controls.bdprochot_disabled(r1fc)

    def fill_profile(self, n: int) -> None:
        """Fill panel from saved profile N (ThrottleStop radio 1-4)."""
        prof = (self.file_cfg.get("profiles") or {}).get(n)
        if not prof:
            self.say(f"profile {n}: empty, keeping panel")
            self.profile = n
            self.sub_title = f"profile {n} (unsaved)"
            return
        base = config.DEFAULT_CONFIG
        uv = prof.get("undervolt", {})
        for p in regs.PLANE_NAMES:
            self._set(f"uv-{p}", uv.get(p, base["undervolt"][p]))
        icc = prof.get("iccmax", {})
        for p in ("core", "cache"):
            self._set(f"icc-{p}", icc.get(p))
        pw = prof.get("power", {})
        for key in ("pl1_w", "pl1_s", "pl2_w", "pl2_s"):
            self._set(f"in-{key}", pw.get(key))
        for key in ("1c", "2c", "3c", "4c"):
            self._set(f"tb-{key}", (prof.get("turbo") or {}).get("limits", {}).get(key))
        self._set("in-trip", prof.get("trip_temp_c"))
        self._set("in-multi", prof.get("multiplier"))
        self.query_one("#ck-turbo", Checkbox).value = bool((prof.get("turbo") or {}).get("disable", False))
        if "eist_enable" in prof:
            self.query_one("#ck-eist", Checkbox).value = bool(prof["eist_enable"])
        self.query_one("#ck-bd", Checkbox).value = bool(prof.get("bdprochot_disable", False))
        self.profile = n
        self.sub_title = f"profile {n}"
        self.say(f"profile {n} loaded into panel (a = apply)")

    def panel_config(self) -> dict:
        uvs = {}
        for p in regs.PLANE_NAMES:
            v = parse_float(self.query_one(f"#uv-{p}", Input).value)
            uvs[p] = v if v is not None else 0.0
        icc = {}
        for p in ("core", "cache"):
            v = parse_float(self.query_one(f"#icc-{p}", Input).value)
            if v is not None:
                icc[p] = v
        trip = parse_float(self.query_one("#in-trip", Input).value)
        multi = parse_int(self.query_one("#in-multi", Input).value)
        limits = {}
        for key in ("1c", "2c", "3c", "4c"):
            v = parse_int(self.query_one(f"#tb-{key}", Input).value)
            if v is not None:
                limits[key] = v
        return {
            "undervolt": uvs,
            "iccmax": icc,
            "power": {k: parse_float(self.query_one(f"#in-{k}", Input).value)
                      for k in ("pl1_w", "pl1_s", "pl2_w", "pl2_s")},
            "turbo": {"disable": self.query_one("#ck-turbo", Checkbox).value, "limits": limits},
            "bdprochot_disable": self.query_one("#ck-bd", Checkbox).value,
            "eist_enable": self.query_one("#ck-eist", Checkbox).value,
            "trip_temp_c": int(trip) if trip is not None else None,
            "multiplier": multi,
            "clockmod_full": True,
        }

    def refresh_rows(self) -> None:
        try:
            cpus = msr.cpu_list()
            cur = monitor.sample_counters(cpus)
            now = time.monotonic()
            dt = now - self.prev_t if self.prev_t else 0.0
            eff, c0p = {}, {}
            if self.prev is not None and dt > 0:
                for c in cpus:
                    a0, m0 = self.prev[c]
                    a1, m1 = cur[c]
                    eff[c] = monitor.effective_mhz(a0, m0, a1, m1, self.base_mhz)
                    c0p[c] = monitor.c0_percent(monitor.counter_delta(m0, m1), dt, self.base_mhz)
            self.prev, self.prev_t = cur, now
            mods = {c: controls.clockmod_percent(msr.read_msr(regs.IA32_CLOCK_MODULATION, c))
                    for c in cpus}
            table = self.query_one("#cores", DataTable)
            for r in monitor.sample_once(cpus):
                table.update_cell(str(r["cpu"]), "ratio", str(r["mhz"]))
                table.update_cell(str(r["cpu"]), "eff", f"{eff[r['cpu']]:.0f}" if r["cpu"] in eff else "-")
                table.update_cell(str(r["cpu"]), "c0", f"{c0p[r['cpu']]:.1f}" if r["cpu"] in c0p else "-")
                table.update_cell(str(r["cpu"]), "mod", f"{mods[r['cpu']]:.0f}")
                t = f"{r['temp']}C" if r["temp"] is not None else "n/a"
                table.update_cell(str(r["cpu"]), "temp", t)
                table.update_cell(str(r["cpu"]), "lim", ",".join(r["limits"]) if r["limits"] else "OK")
            self.sub_title = f"profile {self.profile} | " + package_line()
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
            self.action_save()
        elif event.button.id == "btn-reset":
            self.action_reset()

    async def on_key(self, event) -> None:
        if event.key in ("1", "2", "3", "4"):
            self.fill_profile(int(event.key))

    def action_apply(self) -> None:
        self.do_apply()

    def action_save(self) -> None:
        try:
            config.save_profile(self.panel_config(), self.profile)
            self.file_cfg = config.load_config()
            self.say(f"saved profile {self.profile} -> {config.CONFIG_PATH}")
        except Exception as e:  # noqa: BLE001
            self.say(f"save failed: {e}")

    def action_reset(self) -> None:
        try:
            for line in engine.reset_from_snapshot():
                self.say(line)
            self.fill_hardware()
        except Exception as e:  # noqa: BLE001
            self.say(f"reset failed: {e}")


def run_tui(interval: float = 1.0) -> int:
    engine.require_root()
    TsApp(interval).run()
    return 0
