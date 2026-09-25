#!/bin/sh
# Backups diarios de la base con pg_dump (formato custom) y rotación.
# Variables: POSTGRES_*, BACKUP_HORA (HH:MM, hora del negocio),
# BACKUP_RETENCION_DIAS, BACKUP_AHORA=1 (dump inmediato al arrancar).
set -u

# Variables obligatorias: sin ellas pg_dump no puede conectar. Se validan acá,
# antes de cualquier otra cosa, para cortar con un mensaje claro en el log en
# vez de morir en silencio por "unbound variable" (set -u) y crashear en loop.
: "${POSTGRES_HOST:?[backup] falta POSTGRES_HOST en .env}"
: "${POSTGRES_USER:?[backup] falta POSTGRES_USER en .env}"
: "${POSTGRES_PASSWORD:?[backup] falta POSTGRES_PASSWORD en .env}"
: "${POSTGRES_DB:?[backup] falta POSTGRES_DB en .env}"

HORA="${BACKUP_HORA:-03:00}"
RETENCION="${BACKUP_RETENCION_DIAS:-14}"

# BACKUP_HORA mal formado hace que "objetivo" (más abajo) sea una fecha
# inválida y que `sleep` reciba un número negativo o vacío: dispara dumps
# en loop sin parar. Se valida ACÁ, antes de programar nada, y se corta con
# un mensaje claro y código de salida != 0.
case "$HORA" in
    [0-2][0-9]:[0-5][0-9]) ;;
    *)
        echo "[backup] BACKUP_HORA inválido: '$HORA' (formato esperado HH:MM, 00-23:00-59)" >&2
        exit 1
        ;;
esac
if [ "$(echo "$HORA" | cut -d: -f1)" -gt 23 ]; then
    echo "[backup] BACKUP_HORA inválido: '$HORA' (formato esperado HH:MM, 00-23:00-59)" >&2
    exit 1
fi

case "$RETENCION" in
    ''|*[!0-9]*)
        echo "[backup] BACKUP_RETENCION_DIAS inválido: '$RETENCION' (debe ser un entero positivo)" >&2
        exit 1
        ;;
esac
if [ "$RETENCION" -le 0 ]; then
    echo "[backup] BACKUP_RETENCION_DIAS inválido: '$RETENCION' (debe ser un entero positivo)" >&2
    exit 1
fi

DESTINO=/backups
export PGPASSWORD="$POSTGRES_PASSWORD"

hacer_backup() {
    archivo="$DESTINO/gestion-$(date +%Y-%m-%d_%H%M).dump"
    if pg_dump -Fc -h "$POSTGRES_HOST" -p "${POSTGRES_PORT:-5432}" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f "$archivo.tmp"; then
        if mv "$archivo.tmp" "$archivo"; then
            echo "[backup] OK $archivo"
        else
            rm -f "$archivo.tmp"
            echo "[backup] ERROR al mover $archivo.tmp a $archivo"
        fi
    else
        rm -f "$archivo.tmp"
        echo "[backup] ERROR al generar $archivo"
    fi
    # Rotación: borra dumps con más de RETENCION días.
    find "$DESTINO" -name 'gestion-*.dump' -mmin +"$((RETENCION * 1440))" -print -delete
}

mkdir -p "$DESTINO"
# Limpia .tmp huérfanos de una corrida interrumpida: solo hay un dump a la vez,
# así que cualquier .tmp presente al arrancar es basura de una corrida anterior
# que no llegó a terminar (el contenedor se reinició a mitad de un pg_dump).
find "$DESTINO" -name 'gestion-*.dump.tmp' -print -delete
echo "[backup] programado todos los días a las $HORA, retención $RETENCION días"
[ "${BACKUP_AHORA:-0}" = "1" ] && hacer_backup

while true; do
    ahora=$(date +%s)
    objetivo=$(date -d "$(date +%Y-%m-%d) $HORA" +%s)
    [ "$objetivo" -le "$ahora" ] && objetivo=$(date -d "tomorrow $HORA" +%s)
    sleep $((objetivo - ahora))
    hacer_backup
done
