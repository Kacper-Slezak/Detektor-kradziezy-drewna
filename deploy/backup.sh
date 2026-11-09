#!/bin/sh
# Kopia bazy produkcyjnej: pg_dump (format custom) do $BACKUP_DIR, zostaje 7 najnowszych.
# Odtworzenie: docs/wdrozenie.md, sekcja „Kopie zapasowe”.
#
# cron na serwerze (crontab -e), codziennie o 3:30:
#   30 3 * * * $HOME/Detektor-kradziezy-drewna/deploy/backup.sh >> $HOME/backups/backup.log 2>&1
set -eu

cd "$(dirname "$0")"
DIR="${BACKUP_DIR:-$HOME/backups}"
KEEP="${BACKUP_KEEP:-7}"
mkdir -p "$DIR"

FILE="$DIR/detektor-$(date +%Y%m%d-%H%M%S).dump"
# najpierw do .tmp: przerwany zrzut nie udaje pełnej kopii.
# stderr pokazujemy tylko przy błędzie: TimescaleDB zawsze ostrzega o „circular foreign-key
# constraints” w swoich tabelach katalogowych, co jest nieszkodliwe (odtworzenie działa).
if ! docker compose -f compose.prod.yml exec -T db pg_dump -U detektor -d detektor -Fc \
    > "$FILE.tmp" 2> "$DIR/.pg_dump.err"; then
    cat "$DIR/.pg_dump.err" >&2
    rm -f "$FILE.tmp"
    exit 1
fi
mv "$FILE.tmp" "$FILE"

# usuń starsze niż KEEP najnowszych (nazwy plików są z daty, więc ls jest bezpieczne)
# shellcheck disable=SC2012
ls -1t "$DIR"/detektor-*.dump | tail -n +"$((KEEP + 1))" | while read -r old; do rm -f -- "$old"; done

echo "$(date -Iseconds) OK $FILE $(du -h "$FILE" | cut -f1)"
