import pytest

from src.core.utils import clean_token


@pytest.mark.parametrize(
    "token, expected",
    [
        ("Hello<dummy42>World", "HelloWorld"),
        ("<dummy42>", ""),
        ("prefix<dummy999>suffix", "prefixsuffix"),
    ],
)
def test_clean_token_removes_dummy_tags(token, expected):
    assert clean_token(token) == expected


