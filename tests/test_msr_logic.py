from tslinux import controls, cpu, power, undervolt


def test_undervolt_roundtrip():
    for mv in (0.0, -25.0, -80.5, -100.0):
        for plane in ("core", "cache", "gpu", "agent", "analog"):
            raw = undervolt.encode_write(plane, mv) & 0xFFFFFFFF
            assert abs(undervolt.decode_mv(raw) - mv) < 1.0


def test_undervolt_rejects_positive():
    try:
        undervolt.encode_write("core", 10.0)
    except ValueError:
        return
    raise AssertionError("positive offset accepted")


def test_power_encode_decode():
    val = power.encode(90, 0x12, 110, 0x08)
    d = power.decode(val)
    assert (d["pl1_w_ticks"], d["pl2_w_ticks"]) == (90, 110)
    assert d["locked"] == 0


def test_power_rejects_zero():
    try:
        power.encode(0, 0, 10, 0)
    except ValueError:
        return
    raise AssertionError("0W accepted")


def test_time_window_roundtrip():
    y, z = power.time_window_to_yz(28.0, 1.0 / 1024)
    f = power.yz_to_field(y, z)
    assert power.field_to_seconds(f, 1.0 / 1024) >= 28.0


def test_turbo_limit_encode():
    cur = 0x26262524
    new = cpu.encode_turbo_limit({"1c": 38}, cur)
    assert cpu.decode_turbo_limit(new)["1c"] == 38
    assert cpu.decode_turbo_limit(new)["4c"] == cpu.decode_turbo_limit(cur)["4c"]


def test_controls_bits():
    assert controls.turbo_disabled(controls.set_turbo(0, True))
    assert not controls.turbo_disabled(controls.set_turbo(1 << 38, False))
    assert controls.bdprochot_disabled(controls.set_bdprochot(0xFFFFFFFF, True))
    assert controls.clockmod_percent(controls.clockmod_full(0x10)) == 100.0


def test_trip_offset():
    raw = 0x640000 | (100 << 16)  # tj=100, offset 0
    new = controls.set_trip_offset(raw, 85)
    assert cpu.trip_temp_c(new) == 85
