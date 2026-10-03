"""TUI boots against a fake backend (no root, no hardware)."""
import asyncio

from test_engine import FakeMsr, unlocked_610

from tslinux import engine, monitor, regs
from tslinux import tui as tuimod


def _seed(f):
    f.regs[(regs.MSR_PLATFORM_INFO, 0)] = 28 << 8
    f.regs[(regs.MSR_RAPL_POWER_UNIT, 0)] = 0xA0E03
    f.regs[(regs.MSR_PKG_POWER_LIMIT, 0)] = unlocked_610()
    f.regs[(regs.MSR_TURBO_RATIO_LIMIT, 0)] = 0x24252426
    f.regs[(regs.IA32_MISC_ENABLE, 0)] = 0
    f.regs[(regs.MSR_POWER_CTL, 0)] = 1
    f.regs[(regs.IA32_CLOCK_MODULATION, 0)] = 0x02
    f.regs[(regs.MSR_TEMPERATURE_TARGET, 0)] = 100 << 16
    f.regs[(regs.IA32_PERF_STATUS, 0)] = 28 << 8
    f.regs[(regs.IA32_THERM_STATUS, 0)] = (1 << 31) | (40 << 16)
    f.regs[(regs.IA32_APERF, 0)] = 1000
    f.regs[(regs.IA32_MPERF, 0)] = 1000


def test_tui_boots_and_renders_rows(monkeypatch):
    f = FakeMsr()
    f.cpus = [0]
    _seed(f)
    monkeypatch.setattr(engine, "msr", f)
    monkeypatch.setattr(monitor, "msr", f)
    monkeypatch.setattr(tuimod, "msr", f)
    monkeypatch.setattr(engine, "require_root", lambda: None)

    async def main():
        app = tuimod.TsApp(interval=100.0)
        async with app.run_test() as pilot:
            await pilot.pause()
            table = app.query_one("#cores")
            assert table.row_count == 1

    asyncio.run(main())
