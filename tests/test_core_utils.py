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


@pytest.mark.parametrize("token", ["assistant", "assistent:", "antwort:"])
def test_clean_token_filters_unwanted_tokens(token):
    assert clean_token(token) == ""


@pytest.mark.parametrize(
    "token",
    [
        "Hallo",
        "Antwort",
        "Assistant role",  # Case differences combined with extra text should remain
        "   Leading and trailing whitespace   ",
    ],
)
def test_clean_token_leaves_normal_tokens(token):
    assert clean_token(token) == token
