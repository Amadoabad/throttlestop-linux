# msr-mechanisms

Same-wire MSR mechanisms as ThrottleStop: 0x150 undervolt, 0x610 power,
0x1AD turbo, 0x1A0 turbo-disable, 0x1FC BDPROCHOT, 0x19A clockmod,
0x1A2 trip, monitor via 0x198/0x19C/APERF/MPERF/RAPL. Reset via snapshot;
reboot always resets (no lock bits).
