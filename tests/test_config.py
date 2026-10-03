from tslinux import config


def test_example_loads_with_sane_defaults():
    cfg = config.load_config("etc/tslinux.conf.example")
    assert cfg["undervolt"]["core"] == 0.0
    assert cfg["undervolt"]["cache"] == 0.0
    assert cfg["turbo"]["disable"] is False
    assert cfg["bdprochot_disable"] is False
    assert cfg["power"]["pl1_w"] is None
