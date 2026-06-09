import pytest

from src.core.verification.deterministic import validate_ncm_format


@pytest.mark.parametrize("code", [
    "2202.10.00",  # flavored/sweetened beverages (Ch. 22)
    "2203.00.00",  # malt beers
    "2201.10.00",  # natural mineral water
    "2208.40.00",  # sugarcane spirit (cachaça)
    "0101.21.00",  # different chapter — format still valid
])
def test_accepts_valid_dot_notation(code: str) -> None:
    assert validate_ncm_format(code) is True


@pytest.mark.parametrize("code", [
    "22021000",    # no dots
    "2202.1.00",   # second group with 1 digit
    "2202.10.0",   # third group with 1 digit
    "22022.10.00", # first group with 5 digits
    "2202.10.001", # third group with 3 digits
    "XXXX.XX.XX",  # letters
    "2202.10",     # only two groups
    "",            # empty string
    " 2202.10.00", # leading space
    "2202.10.00 ", # trailing space
])
def test_rejects_malformed_code(code: str) -> None:
    assert validate_ncm_format(code) is False
