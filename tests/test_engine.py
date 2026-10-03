"""Engine behavior against a fake MSR backend (no root needed)."""
import pytest

from tslinux import engine, monitor, regs


class FakeMsr:
    def __init__(self):
        self.regs = {}
        self.writes = []
        self.cpus = [0, 1]

    def cpu_list(self):
        return list(self.cpus)

    def read_msr(self, addr, cpu):
        return self.regs.get((addr, cpu), 0)

    def write_msr(self, addr, value, cpu):
        self.regs[(addr, cpu)] = value & 0xFFFFFFFFFFFFFFFF
        self.writes.append((addr, cpu))


@pytest.fixture
def fake(monkeypatch):
    f = FakeMsr()
    # RAPL units: 0.125 W, time 1/1024 s
    f.regs[(regs.MSR_RAPL_POWER_UNIT, 0)] = 0xA0E03
    f.regs[(regs.MSR_RAPL_POWER_UNIT, 1)] = 0xA0E03
    monkeypatch.setattr(engine, "msr", f)
    return f


def unlocked_610(pl1=376, pl2=470):
    from tslinux import power

    return power.encode(pl1, 0, pl2, 0) & ~(1 << 63)


def test_power_skipped_when_firmware_locked(fake):
    fake.regs[(regs.MSR_PKG_POWER_LIMIT, 0)] = unlocked_610() | (1 << 63)
    msg = engine.apply_power(47, None, None, None)
    assert "lock" in msg
    assert not [w for w in fake.writes if w[0] == regs.MSR_PKG_POWER_LIMIT]


def test_power_writes_when_unlocked(fake):
    fake.regs[(regs.MSR_PKG_POWER_LIMIT, 0)] = unlocked_610()
    msg = engine.apply_power(47, None, None, None)
    assert "PL1=47" in msg
    assert [w for w in fake.writes if w[0] == regs.MSR_PKG_POWER_LIMIT]


def test_clockmod_forced_to_full(fake):
    from tslinux import config as cfgmod

    for c in (0, 1):
        fake.regs[(regs.IA32_CLOCK_MODULATION, c)] = 0x12
        fake.regs[(regs.IA32_MISC_ENABLE, c)] = 0
        fake.regs[(regs.MSR_POWER_CTL, c)] = 1
    fake.regs[(regs.MSR_PLATFORM_INFO, 0)] = 28 << 8
    fake.regs[(regs.MSR_TURBO_RATIO_LIMIT, 0)] = 0x24252426
    fake.regs[(regs.MSR_TEMPERATURE_TARGET, 0)] = (100 << 16)
    fake.regs[(regs.MSR_PKG_POWER_LIMIT, 0)] = unlocked_610()
    cfg = cfgmod.load_config("etc/tslinux.conf.example")
    engine.apply_all(cfg)
    for c in (0, 1):
        assert fake.regs[(regs.IA32_CLOCK_MODULATION, c)] == 0x02


def test_zero_undervolt_touches_no_mailbox(fake):
    assert engine.apply_undervolts({"core": 0.0, "cache": 0.0}) == []
    assert not [w for w in fake.writes if w[0] == regs.MSR_OC_MAILBOX]


def test_effective_mhz_full_speed():
    assert monitor.effective_mhz(0, 0, 2_800_000, 2_800_000, 2800) == pytest.approx(2800)


def test_effective_mhz_clockmodulated():
    # 12.5% duty: APERF advances 1/8 of MPERF
    assert monitor.effective_mhz(0, 0, 350_000, 2_800_000, 2800) == pytest.approx(350)


def test_effective_mhz_zero_window():
    assert monitor.effective_mhz(5, 5, 5, 5, 2800) == 0.0


def test_aperf_mperf_addresses_match_kernel():
    # Pinned against arch/x86/include/asm/msr-index.h (two local kernel
    # builds agree). A swap here inverts the ratio and reports fantasy MHz.
    assert regs.IA32_APERF == 0xE8
    assert regs.IA32_MPERF == 0xE7
