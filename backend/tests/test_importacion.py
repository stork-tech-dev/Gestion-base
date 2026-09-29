"""Importación inicial desde Excel (sesión 08): motor, proveedores y clientes.
Los productos se prueban en la segunda mitad del archivo (Task 2)."""
from io import BytesIO

from openpyxl import Workbook, load_workbook
from sqlalchemy import func, select

from app.core.excel import TIPO_XLSX
from app.models import Auditoria, Cliente, Proveedor

URL = "/api/v1/importacion"
ENCABEZADO_PROVEEDORES = ["nombre", "moneda", "dolar_actual", "pais", "provincia", "telefono", "email", "notas"]
ENCABEZADO_CLIENTES = ["nombre", "dni", "cuit", "condicion_iva", "domicilio", "codigo_postal", "localidad",
                       "telefono", "email"]
CUIT_VALIDO = "20-39059158-7"


def _xlsx(filas) -> bytes:
    libro = Workbook()
    for fila in filas:
        libro.active.append(list(fila))
    salida = BytesIO()
    libro.save(salida)
    return salida.getvalue()


def _subir(client, h, tipo, accion, filas, nombre="datos.xlsx"):
    return client.post(f"{URL}/{tipo}/{accion}", files={"archivo": (nombre, _xlsx(filas), TIPO_XLSX)}, headers=h)


def _contar(db, modelo):
    return db.scalar(select(func.count()).select_from(modelo))


def _admin(crear_usuario, headers_de):
    return headers_de(crear_usuario("admin"))


def test_plantilla_vacia_da_409_y_con_filas_importa(client, crear_usuario, headers_de):
    h = _admin(crear_usuario, headers_de)
    r = client.get(f"{URL}/proveedores/plantilla", headers=h)
    assert r.status_code == 200 and r.headers["content-type"] == TIPO_XLSX
    assert 'filename="importar-proveedores-' in r.headers["content-disposition"]
    libro = load_workbook(BytesIO(r.content))
    assert [c.value for c in libro.worksheets[0][1]] == ENCABEZADO_PROVEEDORES
    assert libro.sheetnames == ["Proveedores", "Instrucciones"]

    r = client.post(f"{URL}/proveedores/importar", files={"archivo": ("p.xlsx", r.content, TIPO_XLSX)}, headers=h)
    assert r.status_code == 409 and r.json()["detail"] == "El archivo no tiene filas para importar."

    libro.worksheets[0].append(["Textil Norte", "Pesos"])
    salida = BytesIO()
    libro.save(salida)
    r = client.post(f"{URL}/proveedores/importar", files={"archivo": ("p.xlsx", salida.getvalue(), TIPO_XLSX)},
                    headers=h)
    assert r.status_code == 200
    assert r.json() == {"tipo": "proveedores", "filas_leidas": 1, "filas_validas": 1, "creados": 1,
                        "categorias_nuevas": [], "errores": [], "aplicado": True}


def test_columnas_en_otro_orden_y_extra(client, db, crear_usuario, headers_de):
    h = _admin(crear_usuario, headers_de)
    filas = [["Columna Extra", "MONEDA", "Nombre", "Dólar Actual"],
             ["x", "Dólares", "Importadora Sur", "1050,5"]]
    r = _subir(client, h, "proveedores", "importar", filas)
    assert r.status_code == 200 and r.json()["creados"] == 1
    proveedor = db.scalar(select(Proveedor).where(Proveedor.nombre == "Importadora Sur"))
    assert proveedor.moneda.value == "usd" and str(proveedor.dolar_actual) == "1050.50"


def test_proveedor_en_dolares_sin_dolar_es_error_de_la_columna(client, crear_usuario, headers_de):
    h = _admin(crear_usuario, headers_de)
    r = _subir(client, h, "proveedores", "validar", [["nombre", "moneda"], ["Sin dolar", "usd"]])
    assert r.status_code == 200
    assert r.json()["errores"] == [
        {"fila": 2, "columna": "dolar_actual", "error": "El valor del dólar debe ser mayor a cero."}]


def test_proveedor_en_pesos_ignora_el_dolar(client, db, crear_usuario, headers_de):
    h = _admin(crear_usuario, headers_de)
    r = _subir(client, h, "proveedores", "importar", [["nombre", "moneda", "dolar_actual"], ["En pesos", "ars", "-3"]])
    assert r.json()["aplicado"] is True
    assert db.scalar(select(Proveedor).where(Proveedor.nombre == "En pesos")).dolar_actual is None


def test_proveedor_duplicado_en_base_y_en_archivo(client, crear_usuario, headers_de):
    h = _admin(crear_usuario, headers_de)
    assert _subir(client, h, "proveedores", "importar", [["nombre", "moneda"], ["Lanas Río", "Pesos"]]).status_code == 200
    filas = [["nombre", "moneda"], ["lanas rio", "Pesos"], ["Nuevo", "Pesos"], ["NUEVO", "Pesos"]]
    errores = _subir(client, h, "proveedores", "validar", filas).json()["errores"]
    assert errores[0]["fila"] == 2 and errores[0]["columna"] is None and "Ya existe un proveedor" in errores[0]["error"]
    assert errores[1] == {"fila": 4, "columna": "nombre", "error": "Repetido en el archivo (fila 3)."}


def test_moneda_invalida_y_varios_errores_de_una_fila(client, crear_usuario, headers_de):
    h = _admin(crear_usuario, headers_de)
    filas = [["nombre", "moneda", "email"], ["x" * 201, "Euros", "no-es-mail"]]
    errores = _subir(client, h, "proveedores", "validar", filas).json()["errores"]
    assert {"fila": 2, "columna": "moneda", "error": "Valor no válido: usá Pesos / Dólares."} in errores
    # moneda falla en el parseo: el alta de esa fila no se intenta, así que no hay error de schema todavía.
    assert len(errores) == 1
    filas = [["nombre", "moneda", "email"], ["x" * 201, "Pesos", "no-es-mail"]]
    errores = _subir(client, h, "proveedores", "validar", filas).json()["errores"]
    assert {"fila": 2, "columna": "nombre", "error": "Admite hasta 200 caracteres."} in errores
    assert {"fila": 2, "columna": "email", "error": "El email no es válido."} in errores


def test_obligatoria_vacia(client, crear_usuario, headers_de):
    h = _admin(crear_usuario, headers_de)
    errores = _subir(client, h, "proveedores", "validar", [["nombre", "moneda"], ["", "Pesos"], ["Ok", None]]).json()["errores"]
    assert errores == [{"fila": 2, "columna": "nombre", "error": "Es obligatoria."},
                       {"fila": 3, "columna": "moneda", "error": "Es obligatoria."}]


def test_cliente_cuit_invalido_y_dni_repetido(client, crear_usuario, headers_de):
    h = _admin(crear_usuario, headers_de)
    assert _subir(client, h, "clientes", "importar", [["nombre", "dni"], ["Ana", 30123456]]).json()["aplicado"]
    filas = [["nombre", "dni", "cuit", "condicion_iva"],
             ["Beto", "30.123.456", None, None],                 # DNI ya en la base
             ["Caro", None, "20-39059158-2", None],                # dígito verificador mal
             ["Dani", 40111222, None, None],
             ["Eli", "40111222", None, None],                    # DNI repetido en el archivo
             ["Fede", None, None, "Responsable inscripto"]]      # sin CUIT y no es consumidor final
    errores = _subir(client, h, "clientes", "validar", filas).json()["errores"]
    assert [(e["fila"], e["columna"]) for e in errores] == [(2, None), (3, None), (5, "dni"), (6, None)]
    assert "ya está cargado" in errores[0]["error"]
    assert "dígito verificador" in errores[1]["error"]
    assert errores[2]["error"] == "Repetido en el archivo (fila 4)."
    assert "CUIT es obligatorio" in errores[3]["error"]


def test_cliente_condicion_por_etiqueta_valor_o_default(client, db, crear_usuario, headers_de):
    h = _admin(crear_usuario, headers_de)
    filas = [["nombre", "cuit", "condicion_iva"],
             ["Uno SA", CUIT_VALIDO, "responsable_inscripto"],
             ["Dos", None, None],
             ["Tres", "27-28033514-8", "monotributista"]]
    r = _subir(client, h, "clientes", "importar", filas)
    assert r.json()["errores"] == [] and r.json()["creados"] == 3
    condiciones = {c.nombre: c.condicion_iva.value for c in db.scalars(select(Cliente)).all()}
    assert condiciones["Uno SA"] == "responsable_inscripto" and condiciones["Dos"] == "consumidor_final"


def test_todo_o_nada(client, db, crear_usuario, headers_de):
    h = _admin(crear_usuario, headers_de)
    antes = _contar(db, Proveedor)
    filas = [["nombre", "moneda"], ["Bueno 1", "Pesos"], ["Malo", "usd"], ["Bueno 2", "Pesos"]]
    r = _subir(client, h, "proveedores", "importar", filas)
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["aplicado"] is False and cuerpo["creados"] == 0
    assert cuerpo["filas_leidas"] == 3 and cuerpo["filas_validas"] == 2 and len(cuerpo["errores"]) == 1
    assert _contar(db, Proveedor) == antes


def test_validar_no_deja_rastros(client, db, crear_usuario, headers_de):
    h = _admin(crear_usuario, headers_de)
    proveedores, auditoria = _contar(db, Proveedor), _contar(db, Auditoria)
    r = _subir(client, h, "proveedores", "validar", [["nombre", "moneda"], ["Solo vista previa", "Pesos"]])
    assert r.json() == {"tipo": "proveedores", "filas_leidas": 1, "filas_validas": 1, "creados": 0,
                        "categorias_nuevas": [], "errores": [], "aplicado": False}
    assert _contar(db, Proveedor) == proveedores
    assert _contar(db, Auditoria) == auditoria


def test_importar_audita_la_importacion_y_cada_alta(client, db, crear_usuario, headers_de):
    h = _admin(crear_usuario, headers_de)
    r = _subir(client, h, "clientes", "importar", [["nombre"], ["Uno"], ["Dos"]], nombre="clientes-viejos.xlsx")
    assert r.json()["creados"] == 2
    registro = db.scalar(select(Auditoria).where(Auditoria.accion == "importacion.clientes"))
    assert registro.estado_nuevo == {"archivo": "clientes-viejos.xlsx", "filas": 2, "creados": 2}
    assert registro.entidad == "importacion" and registro.entidad_id is None
    assert db.scalar(select(func.count()).select_from(Auditoria).where(Auditoria.accion == "cliente.crear")) >= 2


def test_sin_permiso_403_y_tipo_invalido_422(client, crear_usuario, headers_de):
    h = headers_de(crear_usuario("vendedor"))
    assert client.get(f"{URL}/clientes/plantilla", headers=h).status_code == 403
    assert _subir(client, h, "clientes", "validar", [["nombre"], ["x"]]).status_code == 403
    assert _subir(client, h, "clientes", "importar", [["nombre"], ["x"]]).status_code == 403
    h = _admin(crear_usuario, headers_de)
    assert client.get(f"{URL}/ventas/plantilla", headers=h).status_code == 422


def test_archivo_invalido_409(client, crear_usuario, headers_de):
    h = _admin(crear_usuario, headers_de)
    r = client.post(f"{URL}/clientes/validar", files={"archivo": ("x.xlsx", b"basura", TIPO_XLSX)}, headers=h)
    assert r.status_code == 409
    r = _subir(client, h, "clientes", "validar", [["dni"], ["1"]])
    assert r.status_code == 409 and r.json()["detail"] == "Faltan columnas: nombre"
