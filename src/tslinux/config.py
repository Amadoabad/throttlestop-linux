"""Config + defaults snapshot (ThrottleStop.ini parity + true reset).

Config lives at /etc/tslinux.conf (TOML). Defaults snapshot at
/var/lib/tslinux/defaults.json is captured on first apply and used by
`tslinux reset` to restore the machine without rebooting.
Reboot always resets too: none of these MSRs are persistent, and this
tool never sets lock bits.
"""
from __future__ import annotations

import json
import os

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 fallback
    tomllib = None  # type: ignore

CONFIG_PATH = "/etc/tslinux.conf"
SNAPSHOT_PATH = "/var/lib/tslinux/defaults.json"

DEFAULT_CONFIG = {
    "undervolt": {"core": 0.0, "gpu": 0.0, "cache": 0.0, "agent": 0.0, "analog": 0.0},
    "power": {"pl1_w": None, "pl1_s": None, "pl2_w": None, "pl2_s": None},
    "turbo": {"disable": False, "limits": {}},
    "bdprochot_disable": False,
    "trip_temp_c": None,
    "clockmod_full": True,
}


def load_config(path: str = CONFIG_PATH) -> dict:
    cfg = {k: (dict(v) if isinstance(v, dict) else v) for k, v in DEFAULT_CONFIG.items()}
    if not os.path.exists(path):
        return cfg
    if tomllib is None:
        raise RuntimeError("tomllib needs Python >= 3.11 to read config")
    with open(path, "rb") as f:
        data = tomllib.load(f)
    for section in ("undervolt", "power", "turbo"):
        if isinstance(data.get(section), dict):
            cfg[section].update(data[section])
    for key in ("bdprochot_disable", "trip_temp_c", "clockmod_full"):
        if key in data:
            cfg[key] = data[key]
    general = data.get("general", {})
    if isinstance(general, dict):
        for key in ("bdprochot_disable", "trip_temp_c", "clockmod_full"):
            if key in general:
                cfg[key] = general[key]
    return cfg


def save_snapshot(data: dict, path: str = SNAPSHOT_PATH) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def _toml_val(v) -> str:
    if v is None:
        return '""'
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        return repr(v)
    return str(v)


def save_config(cfg: dict, path: str = CONFIG_PATH) -> None:
    """Write our known schema back as TOML (no new dependency)."""
    lines = ["[general]"]
    for key in ("bdprochot_disable", "clockmod_full"):
        lines.append(f"{key} = {_toml_val(cfg.get(key))}")
    if cfg.get("trip_temp_c") is not None:
        lines.append(f"trip_temp_c = {_toml_val(cfg['trip_temp_c'])}")
    lines.append("")
    lines.append("[undervolt]")
    for plane, mv in cfg.get("undervolt", {}).items():
        lines.append(f"{plane} = {_toml_val(mv)}")
    lines.append("")
    lines.append("[power]")
    for key in ("pl1_w", "pl1_s", "pl2_w", "pl2_s"):
        val = cfg.get("power", {}).get(key)
        if val is not None:
            lines.append(f"{key} = {_toml_val(val)}")
    lines.append("")
    lines.append("[turbo]")
    lines.append(f"disable = {_toml_val(cfg.get('turbo', {}).get('disable', False))}")
    limits = cfg.get("turbo", {}).get("limits", {})
    if limits:
        inner = ", ".join(f'"{k}" = {v}' for k, v in limits.items())
        lines.append(f"limits = {{ {inner} }}")
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


def load_snapshot(path: str = SNAPSHOT_PATH) -> dict:
    with open(path) as f:
        return json.load(f)
