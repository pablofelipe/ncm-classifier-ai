from src.core.verification.deterministic import VerificationStatus


def test_verification_status_str_value() -> None:
    # StrEnum contract: str() yields the bare value ("passed"), not the
    # "VerificationStatus.PASSED" repr that a plain (str, Enum) mixin produces.
    # .value matches and str-equality still holds. A future ADR wires this enum
    # into the pipeline / response serialization, so lock the contract now.
    assert VerificationStatus.PASSED.value == "passed"
    assert str(VerificationStatus.PASSED) == "passed"
    assert VerificationStatus.PASSED == "passed"
