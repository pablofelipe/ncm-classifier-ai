import pytest

from src.core.domain.ncm import NCMCode

# ---------------------------------------------------------------------------
# Format validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "code",
    [
        "2202.10.00",  # flavored/sweetened beverages (Ch. 22)
        "2208.40.00",  # sugarcane spirit (cachaça)
        "0101.21.00",  # different chapter — format still valid
    ],
)
def test_accepts_valid_dotted_format(code: str) -> None:
    assert NCMCode(code).dotless is not None


@pytest.mark.parametrize(
    "code",
    [
        "22021000",  # no dots (dotless)
        "2202.1.00",  # second group with 1 digit
        "2202.10.0",  # third group with 1 digit
        "22022.10.00",  # first group with 5 digits
        "2202.10.001",  # third group with 3 digits
        "XXXX.XX.XX",  # letters
        "2202.10",  # only two groups
        "",  # empty string
        " 2202.10.00",  # leading space
        "2202.10.00 ",  # trailing space
    ],
)
def test_rejects_malformed_code(code: str) -> None:
    with pytest.raises(ValueError):
        NCMCode(code)


# ---------------------------------------------------------------------------
# Dotless representation
# ---------------------------------------------------------------------------


def test_dotless_strips_dots() -> None:
    assert NCMCode("2202.10.00").dotless == "22021000"


# ---------------------------------------------------------------------------
# String representation — canonical dotted form
# ---------------------------------------------------------------------------


def test_str_returns_canonical_dotted_form() -> None:
    assert str(NCMCode("2202.10.00")) == "2202.10.00"


# ---------------------------------------------------------------------------
# Hierarchy matching
# ---------------------------------------------------------------------------


def test_matches_heading_true_for_dotted_heading() -> None:
    assert NCMCode("2203.00.00").matches_heading("22.03") is True


def test_matches_heading_true_for_dotless_heading() -> None:
    assert NCMCode("2203.00.00").matches_heading("2203") is True


def test_matches_heading_false_for_different_heading() -> None:
    assert NCMCode("2203.00.00").matches_heading("22.09") is False


# ---------------------------------------------------------------------------
# Equality and hashing — used as a dict key (TIPIIndex, RRF fusion)
# ---------------------------------------------------------------------------


def test_equal_codes_compare_equal() -> None:
    assert NCMCode("2202.10.00") == NCMCode("2202.10.00")


def test_different_codes_compare_unequal() -> None:
    assert NCMCode("2202.10.00") != NCMCode("2203.00.00")


def test_usable_as_dict_key() -> None:
    d = {NCMCode("2202.10.00"): "found"}
    assert d[NCMCode("2202.10.00")] == "found"
