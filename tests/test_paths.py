"""Das Paket findet seinen Checkout — oder sagt laut, dass es keinen hat (#44).

Installiert wird nur editierbar (`src/yulyen_ai/paths.py`). Ein `pip install .`
ohne `-e` legte das Paket nach `site-packages`, und jede Pfadberechnung zeigte
dann still ins Leere. Diese Tests halten fest, dass das beim Import auffällt.
"""

from __future__ import annotations

import pytest

from yulyen_ai.paths import (
    ENSEMBLES_DIR,
    LOCALES_DIR,
    PROJECT_ROOT,
    NotACheckoutError,
    checkout_root,
)


def test_the_root_is_this_checkout():
    assert (PROJECT_ROOT / "config.yaml").is_file()
    assert (ENSEMBLES_DIR / "classic" / "personas_base.yaml").is_file()
    assert (LOCALES_DIR / "de.yaml").is_file()


def test_an_installed_copy_outside_a_checkout_fails_loudly(tmp_path):
    """So sähe `site-packages/yulyen_ai/paths.py` aus: keine Daten daneben."""
    fake = tmp_path / "lib" / "site-packages" / "yulyen_ai" / "paths.py"
    fake.parent.mkdir(parents=True)
    fake.touch()

    with pytest.raises(NotACheckoutError, match="pip install -e"):
        checkout_root(fake)


def test_a_checkout_with_both_data_dirs_is_accepted(tmp_path):
    for d in ("ensembles", "locales"):
        (tmp_path / d).mkdir()
    pkg = tmp_path / "src" / "yulyen_ai" / "paths.py"
    pkg.parent.mkdir(parents=True)
    pkg.touch()

    assert checkout_root(pkg) == tmp_path
