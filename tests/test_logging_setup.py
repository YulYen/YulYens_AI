import logging

import pytest
from config.logging_setup import init_logging


@pytest.fixture
def _restore_loggers():
    """init_logging rewires global loggers; restore them after the test."""
    root = logging.getLogger()
    proxy = logging.getLogger("wiki_proxy")
    saved = {
        "root_handlers": list(root.handlers),
        "root_level": root.level,
        "proxy_handlers": list(proxy.handlers),
        "proxy_level": proxy.level,
        "proxy_propagate": proxy.propagate,
    }
    yield
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()
    for handler in list(proxy.handlers):
        proxy.removeHandler(handler)
        handler.close()
    for handler in saved["root_handlers"]:
        root.addHandler(handler)
    for handler in saved["proxy_handlers"]:
        proxy.addHandler(handler)
    root.setLevel(saved["root_level"])
    proxy.setLevel(saved["proxy_level"])
    proxy.propagate = saved["proxy_propagate"]


def test_init_logging_separates_wiki_proxy_from_main_log(tmp_path, _restore_loggers):
    main_log = tmp_path / "main.log"
    proxy_log = tmp_path / "wiki.log"

    init_logging(
        loglevel="INFO",
        logfile=str(main_log),
        wiki_proxy_logfile=str(proxy_log),
        to_console=False,
    )

    logging.getLogger("core.something").info("Hauptlog-Eintrag")
    logging.getLogger("wiki_proxy").info("Proxy-Eintrag")

    main_text = main_log.read_text(encoding="utf-8")
    proxy_text = proxy_log.read_text(encoding="utf-8")

    assert "Hauptlog-Eintrag" in main_text
    assert "Proxy-Eintrag" in proxy_text
    # Isolation in both directions
    assert "Proxy-Eintrag" not in main_text
    assert "Hauptlog-Eintrag" not in proxy_text
    assert logging.getLogger("wiki_proxy").propagate is False


def test_init_logging_respects_loglevel(tmp_path, _restore_loggers):
    main_log = tmp_path / "main.log"

    init_logging(
        loglevel="WARNING",
        logfile=str(main_log),
        wiki_proxy_logfile=str(tmp_path / "wiki.log"),
        to_console=False,
    )

    logging.getLogger("core.x").info("unterhalb der Schwelle")
    logging.getLogger("core.x").warning("wichtig")

    text = main_log.read_text(encoding="utf-8")
    assert "wichtig" in text
    assert "unterhalb der Schwelle" not in text


def test_init_logging_reinit_does_not_duplicate_handlers(tmp_path, _restore_loggers):
    for _ in range(3):
        init_logging(
            loglevel="INFO",
            logfile=str(tmp_path / "main.log"),
            wiki_proxy_logfile=str(tmp_path / "wiki.log"),
            to_console=True,
        )

    root = logging.getLogger()
    # exactly one file handler + one console handler
    assert len(root.handlers) == 2
    assert len(logging.getLogger("wiki_proxy").handlers) == 1
