"""MSR addresses. Sources: Intel SDM Vol.4, intel-undervolt, throttled.

Only addresses with at least two public corroborations are written by
this tool. Uncertain ones are read-only in `monitor`.
"""
# Identity / turbo
MSR_PLATFORM_INFO = 0xCE
MSR_TURBO_RATIO_LIMIT = 0x1AD
IA32_MISC_ENABLE = 0x1A0
MISC_ENABLE_TURBO_DISABLE_BIT = 38

# Perf / clocks
IA32_PERF_CTL = 0x199
IA32_PERF_STATUS = 0x198
IA32_CLOCK_MODULATION = 0x19A
IA32_APERF = 0xE7
IA32_MPERF = 0xE8

# Thermal
IA32_THERM_STATUS = 0x19C
IA32_PACKAGE_THERM_STATUS = 0x1B1
MSR_TEMPERATURE_TARGET = 0x1A2

# Voltage / power
MSR_OC_MAILBOX = 0x150
MSR_RAPL_POWER_UNIT = 0x606
MSR_PKG_POWER_LIMIT = 0x610
MSR_PKG_ENERGY_STATUS = 0x611
MSR_DRAM_ENERGY_STATUS = 0x619
MSR_PP1_ENERGY_STATUS = 0x641  # graphics
MSR_CONFIG_TDP_CONTROL = 0x64B

# Throttling / C-states
MSR_POWER_CTL = 0x1FC  # bit 0: BD PROCHOT (cleared = disabled, per throttled)
MSR_PKG_CST_CONFIG = 0xE2

# Voltage planes (ThrottleStop FIVR order, Haswell)
PLANES = {"core": 0, "gpu": 1, "cache": 2, "agent": 3, "analog": 4}
PLANE_NAMES = ["core", "gpu", "cache", "agent", "analog"]
