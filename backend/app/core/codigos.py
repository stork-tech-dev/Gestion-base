"""Funciones puras de códigos: SKU correlativo, dígito verificador módulo 11
(código de etiqueta) y CUIT. Sin base de datos: se testean aisladas."""
import re
import string

LETRAS = string.ascii_uppercase
NUMEROS_POR_BLOQUE = 999                       # 001..999 por cada par de letras
MAXIMO_SKU = len(LETRAS) ** 2 * NUMEROS_POR_BLOQUE   # 675.324 → ZZ999
_PATRON_SKU = re.compile(r"^[A-Z]{2}[0-9]{3}$")
_ALFABETO = string.digits + LETRAS             # base36: dígitos = su valor, letras desde 10
_PESOS_CUIT = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)


class CodigoInvalido(ValueError):
    """SKU fuera de rango o con formato inválido."""


def codificar_sku(n: int) -> str:
    """Correlativo de la SEQUENCE → 2 letras + 3 dígitos (1 → AA001, 1000 → AB001)."""
    if not 1 <= n <= MAXIMO_SKU:
        raise CodigoInvalido("Se agotaron los códigos de producto disponibles.")
    bloque, numero = divmod(n - 1, NUMEROS_POR_BLOQUE)
    return f"{LETRAS[bloque // len(LETRAS)]}{LETRAS[bloque % len(LETRAS)]}{numero + 1:03d}"


def decodificar_sku(sku: str) -> int:
    """Inverso de codificar_sku."""
    sku = (sku or "").strip().upper()
    if not _PATRON_SKU.match(sku) or sku[2:] == "000":
        raise CodigoInvalido(f"'{sku}' no es un SKU válido.")
    bloque = LETRAS.index(sku[0]) * len(LETRAS) + LETRAS.index(sku[1])
    return bloque * NUMEROS_POR_BLOQUE + int(sku[2:])


def digito_verificador(codigo: str) -> str:
    """Módulo 11 sobre el código en base36, pesos 2..7 cíclicos desde la derecha.
    v = 11 − (suma % 11): 11 → '0', 10 → 'X', si no el dígito."""
    suma = 0
    for posicion, caracter in enumerate(reversed(codigo.upper())):
        try:
            valor = _ALFABETO.index(caracter)
        except ValueError:
            raise CodigoInvalido(f"Carácter '{caracter}' no válido en base36.")
        suma += valor * (2 + posicion % 6)
    v = 11 - suma % 11
    if v == 11:
        return "0"
    if v == 10:
        return "X"
    return str(v)


def codigo_es_valido(codigo_con_verificador: str) -> bool:
    """¿El último carácter es el verificador del resto? (lo tipeado o escaneado)."""
    texto = (codigo_con_verificador or "").strip().upper()
    if len(texto) < 2 or any(c not in _ALFABETO for c in texto):
        return False
    return digito_verificador(texto[:-1]) == texto[-1]


def cuit_es_valido(cuit: str) -> bool:
    """11 dígitos (se ignoran guiones y espacios); verificador módulo 11 con
    pesos 5,4,3,2,7,6,5,4,3,2. v = 11 → 0; v = 10 → CUIT inválido."""
    digitos = re.sub(r"[\s-]", "", cuit or "")
    if not re.fullmatch(r"[0-9]{11}", digitos):
        return False
    suma = sum(int(d) * p for d, p in zip(digitos[:10], _PESOS_CUIT))
    v = 11 - suma % 11
    if v == 11:
        v = 0
    if v == 10:
        return False
    return v == int(digitos[10])
