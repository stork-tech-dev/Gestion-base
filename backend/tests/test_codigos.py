import pytest

from app.core.codigos import (
    MAXIMO_SKU,
    CodigoInvalido,
    codificar_sku,
    codigo_es_valido,
    cuit_es_valido,
    decodificar_sku,
    digito_verificador,
)


@pytest.mark.parametrize("n, sku", [(1, "AA001"), (999, "AA999"), (1000, "AB001"), (26 * 999, "AZ999"),
                                     (26 * 999 + 1, "BA001"), (MAXIMO_SKU, "ZZ999")])
def test_codificar_y_decodificar_sku(n, sku):
    assert codificar_sku(n) == sku
    assert decodificar_sku(sku) == n


@pytest.mark.parametrize("n", [0, -1, MAXIMO_SKU + 1])
def test_sku_fuera_de_rango(n):
    with pytest.raises(CodigoInvalido):
        codificar_sku(n)


@pytest.mark.parametrize("sku", ["AA000", "A0001", "AAA01", "aa001x", "", "AA1000"])
def test_decodificar_sku_invalido(sku):
    with pytest.raises(CodigoInvalido):
        decodificar_sku(sku)


def test_decodificar_acepta_minusculas():
    assert decodificar_sku("ab001") == 1000


@pytest.mark.parametrize("codigo, digito", [
    ("AB123", "1"),   # 3·2 + 2·3 + 1·4 + 11·5 + 10·6 = 131; 131 % 11 = 10; 11 − 10 = 1
    ("AA001", "9"),   # 112 % 11 = 2 → 9
    ("AA006", "X"),   # 122 % 11 = 1 → 10 → X
    ("AA000", "0"),   # 110 % 11 = 0 → 11 → 0
])
def test_digito_verificador(codigo, digito):
    assert digito_verificador(codigo) == digito


def test_verificador_siempre_un_caracter():
    for n in range(1, 3000):
        assert len(digito_verificador(codificar_sku(n))) == 1


def test_codigo_es_valido():
    assert codigo_es_valido("AB1231")
    assert codigo_es_valido("ab1231")
    assert codigo_es_valido("AA006X") and codigo_es_valido("aa006x")
    assert not codigo_es_valido("AB1232")
    assert not codigo_es_valido("AB123")      # sin verificador: el último carácter no verifica
    assert not codigo_es_valido("")
    assert not codigo_es_valido("A")
    assert not codigo_es_valido("AB-231")


@pytest.mark.parametrize("cuit, valido", [
    ("20172543597", True),     # 136 % 11 = 4 → 7
    ("20-17254359-7", True),
    ("20 17254359 7", True),
    ("20172543598", False),    # dígito incorrecto
    ("2017254359", False),     # 10 dígitos
    ("2017254359A", False),
    ("", False),
])
def test_cuit(cuit, valido):
    assert cuit_es_valido(cuit) is valido


def test_cuit_con_verificador_diez_es_invalido():
    # Buscamos un prefijo cuyo verificador daría 10: ese CUIT no existe.
    pesos = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)
    for n in range(10**9, 10**9 + 500):
        prefijo = f"2{n:09d}"[:10]
        suma = sum(int(d) * p for d, p in zip(prefijo, pesos))
        if 11 - suma % 11 == 10:
            assert not any(cuit_es_valido(prefijo + str(d)) for d in range(10))
            return
    pytest.fail("no se encontró un prefijo con verificador 10")
