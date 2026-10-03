# throttlestop-linux

Native Linux port of **ThrottleStop's mechanisms** — not a copy of its binary,
a clean-room reimplementation of the same RDMSR/WRMSR register writes, so it
runs natively on your machine. Haswell-first (your i7-4810MQ), Intel-generic
where the SDM allows.

## Same mechanism ThrottleStop uses

| ThrottleStop panel | Linux equivalent here | Register |
|---|---|---|
| FIVR undervolt | `apply` / GUI mV boxes | MSR `0x150` OC mailbox, planes core/gpu/cache/agent/analog |
| TPL power limits | `apply` PL1/PL2 + windows | MSR `0x610`, units `0x606` |
| Turbo limits | `apply` turbo limits | MSR `0x1AD` |
| Disable Turbo | checkbox / config | `0x1A0` bit 38 |
| BD PROCHOT | checkbox / config | `0x1FC` bit 0 (clear = disabled) |
| Clock Mod 100% | always on apply | `0x19A` enable bit cleared |
| Temp / PROCHOT offset | `trip_temp_c` | `0x1A2` offset bits |
| Right-panel monitor | `monitor` / GUI right side | `0x198/0x19C/0x1B1/0xE7/0xE8/0x611` |
| Turn On/Off, Save | `apply`, `/etc/tslinux.conf` | same volatile MSRs |
| EC fighting | `daemon` loop | re-apply every N s (like ThrottleStop polling) |

Sources: Intel SDM Vol.4, `intel-undervolt` (`undervolt.c` OC mailbox +
`0x610`/`0x606`/`0x1A2` handling), `throttled` (`throttled.py` MSR table,
mailbox encode, `_encode_pkg_power_limit`, BD PROCHOT bit). No ThrottleStop
binary code is used — only the publicly documented register interface.

## Reset (everything ThrottleStop resets, plus reboot)

- `sudo tslinux reset` restores the first-run snapshot in
  `/var/lib/tslinux/defaults.json` (voltages, `0x610`, `0x1AD`, `0x1A0`,
  `0x1FC`, `0x19A`, `0x1A2`) and clears sticky throttle logs.
- Reboot always resets: all these MSRs are volatile and this tool never
  sets lock bits (`0x610` bit 63, `0xE2` bit 15).
- If you set an unstable undervolt and crash: reboot, lower the magnitude,
  re-apply. That is the same recovery as ThrottleStop.

## Safety

- Requires root (`/dev/cpu/*/msr` is root-only on your CachyOS box).
- Start at `0 mV`, step `-10 mV` under load; keep CORE == CACHE.
- Many newer microcodes lock `0x150` — the tool then reports the failure
  instead of pretending. Your 4810MQ (microcode `0x28`) predates the lock.
- Never raise power/thermal limits beyond your cooling + adapter. Same
  Kill-a-Watt warning ThrottleStop shows applies here.

## Use

```bash
uv sync
uv run pytest -q
sudo uv run tslinux status
sudo uv run tslinux apply --dry-run
sudo cp etc/tslinux.conf.example /etc/tslinux.conf
sudo uv run tslinux apply
sudo uv run tslinux monitor
sudo uv run tslinux reset
sudo uv run tslinux gui
```
