#!/bin/sh
# Backups diarios de la base con pg_dump (formato custom) y rotación.
# Variables: POSTGRES_*, BACKUP_HORA (HH:MM, hora del negocio),
# BACKUP_RETENCION_DIAS, BACKUP_AHORA=1 (dump inmediato al arrancar).
set -u

HORA="${BACKUP_HORA:-03:00}"
RETENCION="${BACKUP_RETENCION_DIAS:-14}"
DESTINO=/backups
export PGPASSWORD="$POSTGRES_PASSWORD"

hacer_backup() {
    archivo="$DESTINO/gestion-$(date +%Y-%m-%d_%H%M).dump"
    if pg_dump -Fc -h "$POSTGRES_HOST" -p "${POSTGRES_PORT:-5432}" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f "$archivo.tmp"; then
        mv "$archivo.tmp" "$archivo"
        echo "[backup] OK $archivo"
    else
        rm -f "$archivo.tmp"
        echo "[backup] ERROR al generar $archivo"
    fi
    # Rotación: borra dumps con más de RETENCION días.
    find "$DESTINO" -name 'gestion-*.dump' -mmin +"$((RETENCION * 1440))" -print -delete
}

mkdir -p "$DESTINO"
echo "[backup] programado todos los días a las $HORA, retención $RETENCION días"
[ "${BACKUP_AHORA:-0}" = "1" ] && hacer_backup

while true; do
    ahora=$(date +%s)
    objetivo=$(date -d "$(date +%Y-%m-%d) $HORA" +%s)
    [ "$objetivo" -le "$ahora" ] && objetivo=$(date -d "tomorrow $HORA" +%s)
    sleep $((objetivo - ahora))
    hacer_backup
done
