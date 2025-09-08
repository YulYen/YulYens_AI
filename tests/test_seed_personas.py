import importlib

def _opts(name: str):
    personas = importlib.import_module("config.personas")
    return personas.get_options(name)

def test_peter_has_seed_42():
    opts = _opts("PETER")
    assert isinstance(opts, dict)
    assert opts.get("seed") == 42

def test_others_have_no_seed_by_default():
    for name in ("LEAH", "DORIS", "POPCORN"):
        opts = _opts(name)
        if opts is None:
            continue
        assert "seed" not in opts