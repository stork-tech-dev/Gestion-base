"""Utilidades transversales (Principio 2: una sola definición)."""
from datetime import datetime
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, Decimal

from sqlalchemy import func

from config import settings

# Misma tabla de reemplazo en Python y en SQL (translate de Postgres; no se
# usa la extensión unaccent porque exige superusuario).
TILDES = "áéíóúüñÁÉÍÓÚÜÑ"
SIN_TILDES = "aeiouunAEIOUUN"
_TABLA_TILDES = str.maketrans(TILDES, SIN_TILDES)

_CENTAVOS = Decimal("0.01")


def ahora() -> datetime:
    """Fecha y hora actual con la zona del negocio (cálculos, JWT)."""
    return datetime.now(settings.TZ)


def ahora_db() -> datetime:
    """Fecha y hora del negocio SIN tzinfo: las columnas son TIMESTAMP sin zona."""
    return ahora().replace(tzinfo=None)


def ip_de_request(request) -> str | None:
    """IP del cliente para auditoría.

    X-Forwarded-For lo controla el cliente: confiar en el primer salto lo hace
    falsificable. Se usa `settings.PROXIES_DE_CONFIANZA` (cantidad de proxies
    inversos PROPIOS delante de la app) para decidir cuánto confiar en XFF:
    - 0 (conexión directa / docker compose local): se ignora XFF, siempre
      `request.client.host`.
    - N>0 (detrás de N proxies propios, ej. Railway o un nginx propio): se
      toma la entrada en la posición `-N` de XFF (la que agregó nuestro
      proxy más externo). Si XFF trae menos de N entradas, se cae a
      `request.client.host`.
    """
    proxies = settings.PROXIES_DE_CONFIANZA
    if proxies > 0:
        reenviada = request.headers.get("x-forwarded-for")
        if reenviada:
            saltos = [s.strip() for s in reenviada.split(",") if s.strip()]
            if len(saltos) >= proxies:
                return saltos[-proxies]
    return request.client.host if request.client else None


def _decimal(valor) -> Decimal:
    return valor if isinstance(valor, Decimal) else Decimal(str(valor))


def redondear(valor, decimales: int = 2) -> Decimal:
    """Redondeo comercial (half-up)."""
    return _decimal(valor).quantize(Decimal(1).scaleb(-decimales), rounding=ROUND_HALF_UP)


def _redondear_al_multiplo(valor, multiplo, modo) -> Decimal:
    valor, multiplo = _decimal(valor), _decimal(multiplo)
    if multiplo <= 0:
        return redondear(valor)
    return ((valor / multiplo).to_integral_value(rounding=modo) * multiplo).quantize(_CENTAVOS, rounding=ROUND_HALF_UP)


def redondear_hacia_arriba(valor, multiplo) -> Decimal:
    """CEIL al múltiplo (precio de venta). Múltiplo <= 0: no redondea (solo a centavos)."""
    return _redondear_al_multiplo(valor, multiplo, ROUND_CEILING)


def redondear_hacia_abajo(valor, multiplo) -> Decimal:
    """FLOOR al múltiplo (precios con descuento). Múltiplo <= 0: no redondea."""
    return _redondear_al_multiplo(valor, multiplo, ROUND_FLOOR)


def normalizar_texto(texto: str | None) -> str | None:
    """Colapsa espacios; un texto vacío pasa a None."""
    if texto is None:
        return None
    limpio = " ".join(texto.split())
    return limpio or None


def capitalizar_inicial(texto: str | None) -> str | None:
    """Solo la primera letra en mayúscula; el resto queda como vino."""
    limpio = normalizar_texto(texto)
    if limpio is None:
        return None
    return limpio[0].upper() + limpio[1:]


def sin_tildes(texto: str | None) -> str | None:
    return texto.translate(_TABLA_TILDES) if texto is not None else None


def sin_tildes_sql(columna):
    """Expresión SQL equivalente a sin_tildes() (para ILIKE insensible a tildes)."""
    return func.translate(columna, TILDES, SIN_TILDES)
