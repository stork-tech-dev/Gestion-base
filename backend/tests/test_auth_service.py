from datetime import timedelta

import pytest
from sqlalchemy import select

from app.core.utils import ahora, ahora_db
from app.models import Auditoria, HistorialAcceso, ResultadoAcceso, Sesion
from app.services import auth


def _ultima_auditoria(db, accion):
    return db.scalar(select(Auditoria).where(Auditoria.accion == accion).order_by(Auditoria.id.desc()))


# ---------- Contraseñas ----------
def test_hash_y_verificacion_de_password():
    h = auth.hash_password("Secreta123")
    assert h.startswith("$2b$") and auth.verificar_password("Secreta123", h)
    assert not auth.verificar_password("otra", h)
    assert not auth.verificar_password("Secreta123", "hash-roto")


# ---------- Tokens ----------
def test_verificar_token_valida_tipo_firma_y_vencimiento(db, crear_usuario):
    usuario = crear_usuario()
    access, refresh, sesion = auth.generar_tokens(db, usuario, "10.0.0.1")
    datos = auth.verificar_token(access, "access")
    assert datos["sub"] == str(usuario.id) and datos["sid"] == sesion.jti
    assert auth.verificar_token(refresh, "refresh")["jti"] == sesion.jti
    with pytest.raises(auth.TokenInvalido):
        auth.verificar_token(access, "refresh")
    with pytest.raises(auth.TokenInvalido):
        auth.verificar_token(access + "x", "access")
    with pytest.raises(auth.TokenInvalido):
        auth.verificar_token(None, "access")
    vencido = auth._codificar({"sub": "1", "tipo": "access", "sid": "x"}, ahora() - timedelta(seconds=1))
    with pytest.raises(auth.TokenInvalido):
        auth.verificar_token(vencido, "access")


def test_generar_tokens_crea_sesion_con_ventana_de_inactividad(db, crear_usuario):
    usuario = crear_usuario()
    _, _, sesion = auth.generar_tokens(db, usuario, "10.0.0.1")
    assert sesion.ip_origen == "10.0.0.1" and not sesion.revocada
    minutos = (sesion.expira_en - sesion.creada_en).total_seconds() / 60
    assert minutos == pytest.approx(30, abs=0.1)


def test_registrar_actividad_corre_la_ventana_con_tope(db, crear_usuario):
    usuario = crear_usuario()
    _, _, sesion = auth.generar_tokens(db, usuario, None)
    # Recién creada: correrla menos de un minuto no escribe.
    anterior = sesion.expira_en
    auth.registrar_actividad(db, sesion)
    assert sesion.expira_en == anterior
    # Con la ventana a punto de vencer, se corre hasta ahora + 30 min.
    sesion.expira_en = ahora_db() + timedelta(minutes=5)
    auth.registrar_actividad(db, sesion)
    assert sesion.expira_en > ahora_db() + timedelta(minutes=29)
    # Tope: nunca más allá de creada_en + 7 días.
    sesion.creada_en = ahora_db() - timedelta(days=7) + timedelta(minutes=10)
    sesion.expira_en = ahora_db()
    auth.registrar_actividad(db, sesion)
    assert sesion.expira_en <= sesion.creada_en + timedelta(days=7)


def test_sesion_vencida_por_inactividad_se_revoca(db, crear_usuario):
    usuario = crear_usuario()
    _, refresh, sesion = auth.generar_tokens(db, usuario, None)
    sesion.expira_en = ahora_db() - timedelta(seconds=1)
    db.flush()
    with pytest.raises(auth.TokenInvalido):
        auth.sesion_vigente(db, refresh)
    assert sesion.revocada


def test_refrescar_access_token(db, crear_usuario):
    usuario = crear_usuario()
    _, refresh, sesion = auth.generar_tokens(db, usuario, None)
    nuevo = auth.refrescar_access_token(db, refresh)
    assert auth.verificar_token(nuevo, "access")["sid"] == sesion.jti
    usuario.activo = False
    db.flush()
    with pytest.raises(auth.TokenInvalido):
        auth.refrescar_access_token(db, refresh)
    assert sesion.revocada


def test_revocar_sesion_es_idempotente(db, crear_usuario):
    usuario = crear_usuario()
    _, refresh, sesion = auth.generar_tokens(db, usuario, None)
    assert auth.revocar_sesion(db, refresh) is sesion and sesion.revocada
    assert auth.revocar_sesion(db, refresh) is sesion
    assert auth.revocar_sesion(db, "basura") is None
    with pytest.raises(auth.TokenInvalido):
        auth.sesion_vigente(db, refresh)


def test_revocar_sesiones_de_usuario(db, crear_usuario):
    usuario = crear_usuario()
    for _ in range(2):
        auth.generar_tokens(db, usuario, None)
    auth.revocar_sesiones_de_usuario(db, usuario.id)
    abiertas = db.scalars(select(Sesion).where(Sesion.usuario_id == usuario.id, Sesion.revocada.is_(False))).all()
    assert abiertas == []


# ---------- Login ----------
def test_login_exitoso_registra_historial_y_auditoria(db, crear_usuario):
    usuario = crear_usuario(username="maria", password="Clave1234")
    assert auth.autenticar_usuario(db, "  MARIA ", "Clave1234", "10.0.0.9") is usuario
    historial = db.scalar(select(HistorialAcceso).where(HistorialAcceso.usuario_id == usuario.id))
    assert historial.resultado is ResultadoAcceso.EXITOSO and historial.ip_origen == "10.0.0.9"
    registro = _ultima_auditoria(db, "auth.login")
    assert registro.usuario_id == usuario.id and registro.ip_origen == "10.0.0.9"


@pytest.mark.parametrize(
    "preparar, username, password, detalle",
    [
        (lambda u: None, "juana", "mala", "Contraseña incorrecta"),
        (lambda u: setattr(u, "activo", False), "juana", "Clave1234", "Usuario inactivo"),
        (lambda u: setattr(u.rol, "activo", False), "juana", "Clave1234", "Rol inactivo"),
    ],
)
def test_login_fallido_registra_el_motivo(db, crear_usuario, preparar, username, password, detalle):
    usuario = crear_usuario(username="juana", password="Clave1234")
    preparar(usuario)
    db.flush()
    with pytest.raises(auth.CredencialesInvalidas) as error:
        auth.autenticar_usuario(db, username, password, None)
    assert error.value.mensaje == "Usuario o contraseña incorrectos"
    historial = db.scalar(select(HistorialAcceso).where(HistorialAcceso.usuario_id == usuario.id))
    assert historial.resultado is ResultadoAcceso.FALLIDO and historial.detalle == detalle
    assert _ultima_auditoria(db, "auth.login_fallido").estado_nuevo["detalle"] == detalle


def test_login_de_usuario_inexistente_solo_audita(db):
    with pytest.raises(auth.CredencialesInvalidas):
        auth.autenticar_usuario(db, "nadie", "x", None)
    registro = _ultima_auditoria(db, "auth.login_fallido")
    assert registro.usuario_id is None
    assert registro.estado_nuevo == {"username": "nadie", "detalle": "Usuario inexistente"}


def test_marcar_acceso(db, crear_usuario):
    usuario = crear_usuario(debe_cambiar=True)
    assert auth.debe_cambiar_password(usuario)
    auth.marcar_acceso(db, usuario)
    assert not auth.debe_cambiar_password(usuario)


# ---------- Recuperación y cambio de contraseña ----------
def test_token_de_reset_es_de_un_solo_uso(db, crear_usuario):
    usuario = crear_usuario()
    token = auth.generar_token_reset(usuario)
    assert auth.validar_token_reset(db, token) is usuario
    auth.cambiar_password(db, usuario, "NuevaClave1", autor_id=usuario.id, ip=None, debe_cambiarla=False)
    with pytest.raises(auth.TokenInvalido):
        auth.validar_token_reset(db, token)


def test_token_de_reset_de_otro_tipo_no_sirve(db, crear_usuario):
    usuario = crear_usuario()
    access, _, _ = auth.generar_tokens(db, usuario, None)
    with pytest.raises(auth.TokenInvalido):
        auth.validar_token_reset(db, access)


def test_cambiar_password_revoca_sesiones_y_audita_sin_la_clave(db, crear_usuario):
    usuario = crear_usuario()
    _, refresh, _ = auth.generar_tokens(db, usuario, None)
    auth.cambiar_password(db, usuario, "OtraClave99", autor_id=None, ip="1.1.1.1", debe_cambiarla=True)
    assert auth.verificar_password("OtraClave99", usuario.password_hash)
    assert usuario.ultimo_acceso is None
    with pytest.raises(auth.TokenInvalido):
        auth.sesion_vigente(db, refresh)
    registro = _ultima_auditoria(db, "usuario.cambiar_password")
    assert registro.entidad_id == usuario.id
    assert "OtraClave99" not in str(registro.estado_nuevo)


def test_solicitar_reset_envia_solo_a_usuarios_activos_con_email(db, crear_usuario):
    """solicitar_reset NO manda el mail (sería un timing oracle): devuelve los
    datos para que el llamador lo mande en segundo plano, después del commit."""
    crear_usuario(username="conmail", email="conmail@example.com")
    crear_usuario(username="sinmail")
    crear_usuario(username="inactivo", email="inactivo@example.com", activo=False)

    resultados = {
        nombre: auth.solicitar_reset(db, nombre, None)
        for nombre in ("conmail", "sinmail", "inactivo", "noexiste")
    }
    assert resultados["conmail"][0] == "conmail@example.com"
    assert resultados["sinmail"] is None
    assert resultados["inactivo"] is None
    assert resultados["noexiste"] is None

    registros = db.scalars(select(Auditoria).where(Auditoria.accion == "auth.reset_solicitar")).all()
    assert len(registros) == 4
    con_envio = {r.estado_nuevo["username"]: r.estado_nuevo["con_envio"] for r in registros}
    assert con_envio == {"conmail": True, "sinmail": False, "inactivo": False, "noexiste": False}


# ---------- Revisión final: fuerza bruta, huella de reset, username auditado ----------
def test_cinco_fallos_bloquean_temporalmente_aun_con_la_clave_correcta(db, crear_usuario):
    usuario = crear_usuario(username="bloqueo", password="Clave1234")
    for _ in range(auth.INTENTOS_MAXIMOS):
        with pytest.raises(auth.CredencialesInvalidas):
            auth.autenticar_usuario(db, "bloqueo", "mala", None)
    with pytest.raises(auth.CredencialesInvalidas) as error:
        auth.autenticar_usuario(db, "bloqueo", "Clave1234", None)
    assert error.value.mensaje == "Usuario o contraseña incorrectos"
    assert _ultima_auditoria(db, "auth.login_fallido").estado_nuevo == {
        "username": "bloqueo", "detalle": "Bloqueado temporalmente"}
    ultimo = db.scalar(select(HistorialAcceso).where(HistorialAcceso.usuario_id == usuario.id)
                       .order_by(HistorialAcceso.id.desc()))
    assert ultimo.detalle == "Bloqueado temporalmente"


def test_los_fallos_de_otro_username_no_bloquean(db, crear_usuario):
    usuario = crear_usuario(username="libre", password="Clave1234")
    for _ in range(auth.INTENTOS_MAXIMOS + 1):
        with pytest.raises(auth.CredencialesInvalidas):
            auth.autenticar_usuario(db, "otro.usuario", "mala", None)
    assert auth.autenticar_usuario(db, "libre", "Clave1234", None) is usuario


def test_los_fallos_viejos_no_bloquean(db, crear_usuario):
    from app.models import Auditoria

    usuario = crear_usuario(username="viejo", password="Clave1234")
    for _ in range(auth.INTENTOS_MAXIMOS):
        db.add(Auditoria(accion="auth.login_fallido", entidad="usuario", estado_nuevo={"username": "viejo"},
                         timestamp=ahora_db() - timedelta(minutes=auth.BLOQUEO_MINUTOS + 1)))
    db.flush()
    assert auth.autenticar_usuario(db, "viejo", "Clave1234", None) is usuario


def test_huella_de_reset_no_expone_el_hash(crear_usuario):
    usuario = crear_usuario()
    huella = auth._huella(usuario)
    assert len(huella) == 16 and huella not in usuario.password_hash


def test_username_invalido_se_audita_como_invalido(db):
    with pytest.raises(auth.CredencialesInvalidas):
        auth.autenticar_usuario(db, "Juan Pérez; DROP", "x", None)
    assert _ultima_auditoria(db, "auth.login_fallido").estado_nuevo["username"] == "(inválido)"
