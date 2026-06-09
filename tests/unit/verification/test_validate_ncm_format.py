import pytest

from src.core.verification.deterministic import validate_ncm_format


@pytest.mark.parametrize("code", [
    "2202.10.00",  # bebidas aromatizadas/açucaradas (Cap. 22)
    "2203.00.00",  # cervejas de malte
    "2201.10.00",  # água mineral natural
    "2208.40.00",  # aguardente de cana (cachaça)
    "0101.21.00",  # capítulo diferente — formato ainda válido
])
def test_accepts_valid_dot_notation(code: str) -> None:
    assert validate_ncm_format(code) is True


@pytest.mark.parametrize("code", [
    "22021000",    # sem pontos
    "2202.1.00",   # segundo grupo com 1 dígito
    "2202.10.0",   # terceiro grupo com 1 dígito
    "22022.10.00", # primeiro grupo com 5 dígitos
    "2202.10.001", # terceiro grupo com 3 dígitos
    "XXXX.XX.XX",  # letras
    "2202.10",     # apenas dois grupos
    "",            # string vazia
    " 2202.10.00", # espaço líder
    "2202.10.00 ", # espaço trailer
])
def test_rejects_malformed_code(code: str) -> None:
    assert validate_ncm_format(code) is False
