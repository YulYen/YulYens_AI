# Tests for Yul Yen's AI Orchestra

The suite never asks a real model. Every test runs against the echo backend
(`core.backend: dummy`), injected fakes or the doubles in `tests/doubles.py`,
so a failure means the code changed — not that a model had a bad day.

Measurements against a real model (eval suite with judge, response times,
blind tasting, injection probe, the live API questions) moved to the project's
lab repository on 2026-11-26. They measure model and prompt, not this code.

---

## Fixtures

### `client`
- A **FastAPI TestClient** built from the real `AppFactory`, with the echo
  backend, `core.include_date` off and the wiki off.
- **Typical usage:** structural and contract tests of `/ask` and `/v1`.

The autouse fixtures in `tests/conftest.py` keep a developer's
`config.local.yaml`, the real conversation store and the internet out of every
test run; their docstrings say why each one exists.

---

## The guard red-team corpus

`test_guard_redteam.py` turns **every case of `tests/guard_redteam.yaml`** into
a parametrized test (loader and evaluator: `tests/guard_corpus.py`). New attack
patterns belong in the YAML, not in the test file. Cases flagged
`known_gap: true` are asserted from the other side — the test fails once a
documented gap is closed, as a reminder to drop the flag — and
`KNOWN_GAP_IDS` pins which gaps exist at all.

Whether the *model* follows a payload that gets through is the lab's question,
not this suite's.

---

## Markers

- `@pytest.mark.slow` — noticeable runtime, e.g. wiki lookups against a local
  proxy. Included in `make test-ci`, left out of `make test`.
- `@pytest.mark.browser` — drives the running WebUI in a real Chromium
  (`make test-browser`, needs Playwright). Excluded from every other target
  and from CI.

```bash
python -m pytest -q -m "not slow and not browser"   # make test
python -m pytest -q -m "not browser"                # make test-ci, without coverage
python -m pytest -q -m browser                      # make test-browser
```

---

## Coverage

`pytest-cov` is part of `requirements-dev.txt`:

```bash
make coverage        # fast lane with coverage report
make test-ci         # same scope as CI (includes 'slow', with coverage)
```

There is deliberately no hard threshold gate (see #64e in the backlog).

---

## Best practices

- **Deterministic assertions:** normalise values (lowercase, Unicode NFKD)
  before comparing.
- **Fix the time zone** for date tests: `zoneinfo.ZoneInfo("Europe/Berlin")`.
- **Doubles from `tests/doubles.py`** (`create_autospec`), never a bare `Mock()`
  — a bare mock is truthy for every attribute.
