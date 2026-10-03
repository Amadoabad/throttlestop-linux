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
    "iccmax": {},
    "power": {"pl1_w": None, "pl1_s": None, "pl2_w": None, "pl2_s": None},
    "turbo": {"disable": False, "limits": {}},
    "bdprochot_disable": False,
    "trip_temp_c": None,
    "clockmod_full": True,
    "multiplier": None,
    "profiles": {},
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
    if "multiplier" in data:
        cfg["multiplier"] = data["multiplier"]
    if isinstance(general, dict) and "multiplier" in general:
        cfg["multiplier"] = general["multiplier"]
    if isinstance(data.get("iccmax"), dict):
        cfg["iccmax"] = dict(data["iccmax"])
    if isinstance(data.get("eist_enable"), bool):
        cfg["eist_enable"] = data["eist_enable"]
    if isinstance(general, dict) and isinstance(general.get("eist_enable"), bool):
        cfg["eist_enable"] = general["eist_enable"]
    # ThrottleStop-style profiles 1-4: [profile.N] + [profile.N.<section>].
    profiles = data.get("profile", {})
    if isinstance(profiles, dict):
        for nkey, val in profiles.items():
            try:
                n = int(nkey)
            except (TypeError, ValueError):
                continue
            if not isinstance(val, dict):
                continue
            prof: dict = {}
            for section in ("undervolt", "iccmax", "power", "turbo"):
                if isinstance(val.get(section), dict):
                    prof[section] = dict(val[section])
            for k in ("bdprochot_disable", "trip_temp_c", "clockmod_full",
                      "multiplier", "eist_enable"):
                if k in val:
                    prof[k] = val[k]
            cfg["profiles"][n] = prof
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
    if cfg.get("multiplier") is not None:
        lines.append(f"multiplier = {_toml_val(cfg['multiplier'])}")
    if isinstance(cfg.get("eist_enable"), bool):
        lines.append(f"eist_enable = {_toml_val(cfg['eist_enable'])}")
    lines.append("")
    lines.append("[undervolt]")
    for plane, mv in cfg.get("undervolt", {}).items():
        lines.append(f"{plane} = {_toml_val(mv)}")
    if cfg.get("iccmax"):
        lines.append("")
        lines.append("[iccmax]")
        for plane, a in cfg["iccmax"].items():
            lines.append(f"{plane} = {_toml_val(a)}")
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


def save_profile(cfg: dict, n: int, path: str = CONFIG_PATH) -> None:
    """Write panel values under [profile.N], preserving the rest of file."""
    try:
        with open(path) as f:
            text = f.read()
    except FileNotFoundError:
        text = ""
    # Drop any existing [profile.N...] blocks.
    out = []
    skip = False
    for line in text.splitlines():
        if line.strip().startswith("["):
            head = line.strip().strip("[]").lower()
            skip = head == f"profile.{n}" or head.startswith(f"profile.{n}.")
        if not skip:
            out.append(line)
    p = f"profile.{n}"
    block = [f"[{p}]"]
    for k in ("bdprochot_disable", "clockmod_full", "trip_temp_c",
              "multiplier", "eist_enable"):
        if cfg.get(k) is not None:
            block.append(f"{k} = {_toml_val(cfg[k])}")
    if cfg.get("undervolt"):
        block += [f"[{p}.undervolt]"] + [
            f"{plane} = {_toml_val(mv)}" for plane, mv in cfg["undervolt"].items()]
    if cfg.get("iccmax"):
        block += [f"[{p}.iccmax]"] + [
            f"{plane} = {_toml_val(a)}" for plane, a in cfg["iccmax"].items()]
    if cfg.get("power") and any(v is not None for v in cfg["power"].values()):
        block += [f"[{p}.power]"] + [
            f"{k} = {_toml_val(v)}" for k, v in cfg["power"].items() if v is not None]
    block += [f"[{p}.turbo]",
              f"disable = {_toml_val(cfg.get('turbo', {}).get('disable', False))}"]
    limits = cfg.get("turbo", {}).get("limits", {})
    if limits:
        inner = ", ".join(f'"{k}" = {v}' for k, v in limits.items())
        block.append(f"limits = {{ {inner} }}")
    text = "\n".join(out).rstrip("\n") + "\n\n" + "\n".join(block) + "\n"
    with open(path, "w") as f:
        f.write(text)


def load_snapshot(path: str = SNAPSHOT_PATH) -> dict:
    with open(path) as f:
        return json.load(f)
