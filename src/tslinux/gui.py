"""Tkinter GUI mimicking ThrottleStop layout (left controls, right monitor).

Stdlib-only so no new dependency. Must run as root to touch MSRs;
otherwise shows the error and stays open for inspection.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk


def run_gui() -> None:
    from . import config, cpu as cpuinfo, controls, engine, msr, power, regs, undervolt

    cfg = config.load_config()
    root = tk.Tk()
    root.title("ThrottleStop Linux (native)")

    left = ttk.Frame(root, padding=8)
    left.grid(row=0, column=0, sticky="nsew")
    right = ttk.Frame(root, padding=8)
    right.grid(row=0, column=1, sticky="nsew")

    turbo_var = tk.BooleanVar(value=bool(cfg["turbo"]["disable"]))
    bd_var = tk.BooleanVar(value=bool(cfg["bdprochot_disable"]))
    uv_vars: dict[str, tk.StringVar] = {}
    ttk.Checkbutton(left, text="Disable Turbo", variable=turbo_var).pack(anchor="w")
    ttk.Checkbutton(left, text="BD PROCHOT disable", variable=bd_var).pack(anchor="w")

    for plane in regs.PLANE_NAMES:
        var = tk.StringVar(value=str(cfg["undervolt"].get(plane, 0.0)))
        uv_vars[plane] = var
        row = ttk.Frame(left)
        row.pack(fill="x")
        ttk.Label(row, text=f"{plane} mV", width=10).pack(side="left")
        ttk.Entry(row, textvariable=var, width=8).pack(side="left")

    pl1_var = tk.StringVar(value=str(cfg["power"].get("pl1_w") or ""))
    pl2_var = tk.StringVar(value=str(cfg["power"].get("pl2_w") or ""))
    for label, var in (("PL1 W", pl1_var), ("PL2 W", pl2_var)):
        row = ttk.Frame(left)
        row.pack(fill="x")
        ttk.Label(row, text=label, width=10).pack(side="left")
        ttk.Entry(row, textvariable=var, width=8).pack(side="left")

    log = tk.Text(right, width=48, height=22)
    log.pack()

    def say(msg: str) -> None:
        log.insert("end", msg + "\n")
        log.see("end")

    def refresh() -> None:
        try:
            cpus = msr.cpu_list()
            c0 = cpus[0]
            lines = []
            for r in __import__("tslinux.monitor", fromlist=["sample_once"]).sample_once(cpus):
                t = f"{r['temp']}C" if r["temp"] is not None else "n/a"
                lim = ",".join(r["limits"]) if r["limits"] else "OK"
                lines.append(f"cpu{r['cpu']}: {r['mhz']}MHz {t} {lim}")
            raw606 = msr.read_msr(regs.MSR_RAPL_POWER_UNIT, c0)
            d = power.decode(msr.read_msr(regs.MSR_PKG_POWER_LIMIT, c0))
            pu = power.power_unit(raw606)
            lines.append(f"PL1 {d['pl1_w_ticks']*pu:.1f}W PL2 {d['pl2_w_ticks']*pu:.1f}W")
            log.delete("1.0", "end")
            say("\n".join(lines))
        except Exception as e:  # noqa: BLE001 - show in GUI
            say(f"error: {e}")
        root.after(2000, refresh)

    def on_apply() -> None:
        try:
            new_cfg = config.load_config()
            new_cfg["turbo"]["disable"] = turbo_var.get()
            new_cfg["bdprochot_disable"] = bd_var.get()
            for plane, var in uv_vars.items():
                new_cfg["undervolt"][plane] = float(var.get() or 0.0)
            new_cfg["power"]["pl1_w"] = float(pl1_var.get()) if pl1_var.get().strip() else None
            new_cfg["power"]["pl2_w"] = float(pl2_var.get()) if pl2_var.get().strip() else None
            import os

            if not os.path.exists(config.SNAPSHOT_PATH):
                config.save_snapshot(engine.capture_defaults())
            for line in engine.apply_all(new_cfg):
                say(line)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Apply failed", str(e))

    def on_reset() -> None:
        try:
            for line in engine.reset_from_snapshot():
                say(line)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Reset failed", str(e))

    btns = ttk.Frame(left)
    btns.pack(fill="x", pady=6)
    ttk.Button(btns, text="Turn On (apply)", command=on_apply).pack(side="left")
    ttk.Button(btns, text="Reset", command=on_reset).pack(side="left")
    ttk.Button(btns, text="Quit", command=root.destroy).pack(side="left")

    refresh()
    root.mainloop()
