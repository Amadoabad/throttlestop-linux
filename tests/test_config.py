from tslinux import config


def test_example_loads_with_sane_defaults():
    cfg = config.load_config("etc/tslinux.conf.example")
    assert cfg["undervolt"]["core"] == 0.0
    assert cfg["undervolt"]["cache"] == 0.0
    assert cfg["turbo"]["disable"] is False
    assert cfg["bdprochot_disable"] is False
    assert cfg["power"]["pl1_w"] is None


def test_save_load_roundtrip(tmp_path):
    from tslinux import config as cfgmod

    cfg = cfgmod.load_config("etc/tslinux.conf.example")
    cfg["undervolt"]["core"] = -50.0
    cfg["power"]["pl1_w"] = 47.0
    cfg["trip_temp_c"] = 95
    cfg["turbo"]["limits"] = {"1c": 38}
    path = str(tmp_path / "tslinux.conf")
    cfgmod.save_config(cfg, path)
    back = cfgmod.load_config(path)
    assert back["undervolt"]["core"] == -50.0
    assert back["power"]["pl1_w"] == 47.0
    assert back["trip_temp_c"] == 95
    assert back["turbo"]["limits"] == {"1c": 38}
