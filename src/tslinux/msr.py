"""Raw MSR access via /dev/cpu/*/msr. Root-only for real hardware.

Why this file exists: ThrottleStop on Windows uses WinRing0 to RDMSR/WRMSR.
On Linux the native equivalent is /dev/cpu/<n>/msr (kernel CONFIG_X86_MSR).
All mechanisms in this project go through this module so the register
addresses stay identical to ThrottleStop's.
"""
from __future__ import annotations

import os
import struct


class MsrError(OSError):
    pass


def cpu_list(sysfs: str = "/dev/cpu") -> list[int]:
    try:
        entries = os.listdir(sysfs)
    except FileNotFoundError:
        return []
    return sorted(int(e) for e in entries if e.isdigit())


def _path(cpu: int) -> str:
    return f"/dev/cpu/{cpu}/msr"


def read_msr(addr: int, cpu: int) -> int:
    """Read 64-bit MSR `addr` on `cpu`. Raises MsrError on failure."""
    try:
        fd = os.open(_path(cpu), os.O_RDONLY)
    except OSError as e:
        raise MsrError(f"cannot open {_path(cpu)} (need root?): {e}") from e
    try:
        data = os.pread(fd, 8, addr)
        if len(data) != 8:
            raise MsrError(f"short read of MSR {addr:#x} on cpu {cpu}")
        return struct.unpack("Q", data)[0]
    except OSError as e:
        raise MsrError(f"cannot read MSR {addr:#x} on cpu {cpu}: {e}") from e
    finally:
        os.close(fd)


def write_msr(addr: int, value: int, cpu: int) -> None:
    """Write 64-bit `value` to MSR `addr` on `cpu`. Raises MsrError."""
    if not 0 <= value <= 0xFFFFFFFFFFFFFFFF:
        raise ValueError(f"value {value:#x} does not fit 64 bits")
    try:
        fd = os.open(_path(cpu), os.O_WRONLY)
    except OSError as e:
        raise MsrError(f"cannot open {_path(cpu)} for write (need root?): {e}") from e
    try:
        os.pwrite(fd, struct.pack("Q", value), addr)
    except OSError as e:
        raise MsrError(f"cannot write MSR {addr:#x} on cpu {cpu}: {e}") from e
    finally:
        os.close(fd)


def read_all(addr: int) -> dict[int, int]:
    return {cpu: read_msr(addr, cpu) for cpu in cpu_list()}


def write_all(addr: int, value: int) -> None:
    for cpu in cpu_list():
        write_msr(addr, value, cpu)


def bits(value: int, lo: int, hi: int) -> int:
    """Extract inclusive bit range [lo, hi]."""
    if not 0 <= lo <= hi <= 63:
        raise ValueError(f"bad bit range [{lo},{hi}]")
    mask = ((1 << (hi - lo + 1)) - 1) << lo
    return (value & mask) >> lo


class MockMsr:
    """In-memory MSR backend for tests (no root, no hardware)."""

    def __init__(self, ncpus: int = 2):
        self.regs: dict[tuple[int, int], int] = {}
        self.ncpus = ncpus

    def read(self, addr: int, cpu: int) -> int:
        return self.regs.get((addr, cpu), 0)

    def write(self, addr: int, value: int, cpu: int) -> None:
        self.regs[(addr, cpu)] = value & 0xFFFFFFFFFFFFFFFF
