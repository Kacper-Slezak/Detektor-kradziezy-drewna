#!/usr/bin/env bash
# Automatyczne wdrożenie: cron co 5 min sprawdza, czy w GHCR są nowe obrazy albo w repo
# nowe pliki deploy/, i tylko wtedy wdraża. Bez zmian kończy się po cichu.
# Instrukcja: docs/wdrozenie.md, sekcja 3.
#
#   */5 * * * * $HOME/Detektor-kradziezy-drewna/deploy/auto-update.sh >> $HOME/deploy.log 2>&1
#
# Przy nowej wersji: backup -> migracje nowym obrazem (stare kontenery dalej działają)
# -> podmiana kontenerów -> czekanie na /health -> przy błędzie powrót do poprzednich
# obrazów. Migracji nie cofamy (do tego jest backup sprzed wdrożenia).
# Wersja, która nie wstała, jest zapamiętana i nie jest wdrażana ponownie.
# TAG=sha-… w .env zatrzymuje automat na tej wersji.
#
# Całość jest w funkcji main: git merge może podmienić ten plik w trakcie działania,
# a bash czyta skrypt kawałkami; funkcję wczytuje w całości przed wykonaniem.

main() {
    set -euo pipefail
    cd "$(dirname "$0")"

    exec 9>"${LOCK_FILE:-/tmp/detektor-auto-update.lock}"
    flock -n 9 || return 0 # poprzednie uruchomienie jeszcze trwa

    C=(docker compose -f compose.prod.yml)
    APP=(web caddy) # serwisy z naszymi obrazami; obraz bazy aktualizujemy ręcznie
    FAILED=.auto-update-failed
    HEALTH_WAIT_S=${HEALTH_WAIT_S:-90}

    # 1. pliki deploy/ (compose, skrypty) z main
    local files_changed=0
    git fetch -q origin main
    if [ "$(git rev-parse HEAD)" != "$(git rev-parse origin/main)" ]; then
        git diff --quiet HEAD origin/main -- . || files_changed=1
        git merge -q --ff-only origin/main
        log "repo: $(git rev-parse --short HEAD)"
    fi

    # 2. obrazy: porównujemy ID pobranego obrazu z ID obrazu działającego kontenera.
    # Przed pobraniem działającą wersję tagujemy jako :previous (po nazwie, bo po
    # pobraniu stary obraz traci nazwę i nie każdy Docker da się wtedy otagować po ID).
    # Gdy działa już :previous (po powrocie), zostawiamy go bez zmian.
    local can_rollback=1 s ref
    for s in "${APP[@]}"; do
        ref=$(image_ref "$s")
        if [ -n "$(running_id "$s")" ] && [ "$(local_id "$ref")" = "$(running_id "$s")" ]; then
            docker tag "$ref" "${ref%:*}:previous"
        fi
        [ -n "$(local_id "${ref%:*}:previous")" ] || can_rollback=0 # pierwsze wdrożenie
    done

    "${C[@]}" pull -q "${APP[@]}"
    local need=$files_changed versions=""
    declare -A old_id
    for s in "${APP[@]}"; do
        ref=$(image_ref "$s")
        old_id[$s]=$(running_id "$s")
        versions+="$s=$(local_id "$ref" | cut -c8-19) "
        [ "$(local_id "$ref")" = "${old_id[$s]}" ] || need=1
    done
    [ "$need" = 1 ] || return 0
    if [ "$files_changed" = 0 ] && [ -f "$FAILED" ] && [ "$(cat "$FAILED")" = "$versions" ]; then
        return 0 # ta wersja już raz nie wstała, czekamy na następną
    fi
    log "nowa wersja: $versions"

    # 3. backup, gdy baza już działa
    if [ -n "$("${C[@]}" ps -q db)" ]; then
        ./backup.sh || {
            log "BŁĄD: backup nieudany, wdrożenie przerwane"
            return 1
        }
    fi

    # 4. migracje nowym obrazem; przy błędzie zostaje poprzednia wersja
    if ! "${C[@]}" run --rm -T web alembic upgrade head; then
        echo "$versions" >"$FAILED"
        log "BŁĄD: migracje nieudane, zostaje poprzednia wersja"
        return 1
    fi

    # 5. podmiana kontenerów i czekanie na /health
    "${C[@]}" up -d
    if wait_healthy; then
        rm -f "$FAILED"
        docker image prune -f >/dev/null
        log "OK: wdrożone ($versions)"
        return 0
    fi

    echo "$versions" >"$FAILED"
    if [ "$can_rollback" = 1 ]; then
        log "BŁĄD: /health nie odpowiada po ${HEALTH_WAIT_S} s, powrót do poprzednich obrazów (migracje NIE są cofnięte)"
        TAG=previous "${C[@]}" up -d "${APP[@]}"
        if wait_healthy; then
            log "powrót OK: działa poprzednia wersja"
        else
            log "BŁĄD: poprzednia wersja też nie odpowiada, potrzebna ręczna interwencja"
        fi
    else
        log "BŁĄD: /health nie odpowiada po ${HEALTH_WAIT_S} s, brak poprzedniej wersji do powrotu"
    fi
    return 1
}

log() { echo "$(date -Iseconds) $*"; }

image_ref() { # obraz serwisu z compose, z TAG i REGISTRY z .env
    "${C[@]}" config --format json |
        python3 -c 'import json, sys; print(json.load(sys.stdin)["services"][sys.argv[1]]["image"])' "$1"
}

running_id() { # ID obrazu działającego kontenera; pusty, gdy kontener nie działa
    local cid
    cid=$("${C[@]}" ps -q "$1")
    if [ -n "$cid" ]; then docker inspect -f '{{.Image}}' "$cid"; fi
}

local_id() { docker image inspect -f '{{.Id}}' "$1" 2>/dev/null || true; }

wait_healthy() { # do HEALTH_WAIT_S sekund
    local waited=0
    until healthy; do
        [ "$waited" -lt "$HEALTH_WAIT_S" ] || return 1
        sleep 5
        waited=$((waited + 5))
    done
}

healthy() {
    "${C[@]}" exec -T web python -c \
        "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=3)" \
        >/dev/null 2>&1
}

main "$@"
exit $?
