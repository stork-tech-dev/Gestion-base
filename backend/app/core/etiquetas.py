"""Textos legibles de los enums: ÚNICA definición. Los usan las pantallas
(selects y filtros, vía app/api/pages.py) y la importación desde Excel (que
acepta la etiqueta o el valor)."""
from app.models import CondicionIva, Moneda, TemporadaProducto

MONEDAS = [
    (Moneda.ARS.value, "Pesos"),
    (Moneda.USD.value, "Dólares"),
]
CONDICIONES_IVA = [
    (CondicionIva.CONSUMIDOR_FINAL.value, "Consumidor final"),
    (CondicionIva.RESPONSABLE_INSCRIPTO.value, "Responsable inscripto"),
    (CondicionIva.MONOTRIBUTISTA.value, "Monotributista"),
    (CondicionIva.EXENTO.value, "Exento"),
]
TEMPORADAS = [
    (TemporadaProducto.ATEMPORAL.value, "Atemporal"),
    (TemporadaProducto.OTONO_INVIERNO.value, "Otoño-Invierno"),
    (TemporadaProducto.PRIMAVERA_VERANO.value, "Primavera-Verano"),
]
