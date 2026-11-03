"""Symulator wirtualnych czujników: wysyła ramki na POST /api/v1/ingest tak, jak zrobi to firmware.

Ramki są pakowane tym samym koderem co w seedzie (app/protocol/encoder.py), więc przechodzą
przez dekoder, wykrywanie duplikatów, wyciszanie i scalanie alarmów jak prawdziwe dane.

Przykłady (z katalogu backend/, w Dockerze: `docker compose --profile sim up simulator`):

    python -m tools.simulator                                  # czujniki demo, heartbeat co 30 s
    python -m tools.simulator --scenario theft                 # kradzież na pierwszym czujniku
    python -m tools.simulator --scenario battery-drain --target 70B3D57ED00D0009
    python -m tools.simulator --sensors 70B3D57ED0051234 --interval 5 --once

Scenariusze (dotyczą czujnika --target, reszta wysyła zwykłe heartbeaty):
    normal         heartbeaty + losowo co jakiś czas kradzież (--alarm-chance)
    theft          ALARM 3 razy (mikrofon + wibracje, wysoka pewność) na starcie
    false-alarm    ALARM 3 razy (same wibracje, niska pewność) na starcie
    battery-drain  bateria spada o 5 pkt przy każdym heartbeacie
    silent         czujnik przestaje nadawać (po ~12 h w bazie będzie "silent")
    duplicate      każda ramka wysłana dwa razy; backend ma odpowiedzieć "duplicate"

Licznik i bateria każdego czujnika są zapisywane w pliku stanu (--state), bo w firmware
licznik też przetrwa restart. Na starcie każdy czujnik wysyła BOOT, jak po włączeniu.
"""

import argparse
import asyncio
import json
import logging
import random
from dataclasses import asdict, dataclass
from pathlib import Path

import httpx

from app.demo import DEMO_SENSORS
from app.protocol.encoder import encode_alarm, encode_boot, encode_heartbeat

log = logging.getLogger("simulator")

INGEST_PATH = "/api/v1/ingest"
SCENARIOS = ["normal", "theft", "false-alarm", "battery-drain", "silent", "duplicate"]
# czujniki demo z lokalizacją i włączone (te, które w terenie by nadawały)
DEFAULT_SENSORS = [
    s.id
    for s in DEMO_SENSORS
    if s.lat is not None and s.scenario not in ("off", "silent")
]
# bateria na start (bez pliku stanu): dla czujników demo mniej więcej tyle, ile zostawił seed
START_BATTERY = {s.id: max(1, s.battery_start - 15) for s in DEMO_SENSORS}


@dataclass
class VirtualSensor:
    id: str
    counter: int = 0
    battery: int = 95
    silent: bool = False

    def next_counter(self) -> int:
        self.counter = (self.counter + 1) % (1 << 16)
        return self.counter


class Simulator:
    def __init__(
        self,
        client: httpx.AsyncClient,
        sensors: list[VirtualSensor],
        *,
        rng: random.Random | None = None,
        repeat_gap_s: float = 5.0,
        duplicate: bool = False,
    ):
        self.client = client
        self.sensors = sensors
        self.rng = rng or random.Random()
        self.repeat_gap_s = repeat_gap_s
        self.duplicate = duplicate
        self.drain: set[str] = set()

    async def send(self, sensor: VirtualSensor, payload: bytes) -> list[dict]:
        """Wysyła ramkę (przy --scenario duplicate dwa razy). Zwraca odpowiedzi backendu."""
        body = {
            "device": sensor.id,
            "payload_hex": payload.hex(),
            "rssi": self.rng.randint(-120, -95),
        }
        results = []
        for _ in range(2 if self.duplicate else 1):
            try:
                r = await self.client.post(INGEST_PATH, json=body)
            except httpx.TransportError as e:
                # backend się restartuje (--reload) albo jeszcze nie wstał: ramka przepada,
                # jak przy zgubionej transmisji LoRa, a symulator działa dalej
                log.warning(
                    "%s: backend nie odpowiada (%s)", sensor.id, type(e).__name__
                )
                continue
            if r.status_code == 404:
                log.error(
                    "%s: backend nie zna czujnika. Uruchom seed --demo albo dodaj go w panelu.",
                    sensor.id,
                )
            elif r.status_code >= 500:
                log.error(
                    "%s: błąd serwera %s. Czy baza ma tabele? "
                    "docker compose run --rm web alembic upgrade head",
                    sensor.id,
                    r.status_code,
                )
            elif r.status_code >= 400:
                log.error("%s: %s %s", sensor.id, r.status_code, r.text)
            else:
                data = r.json()
                log.info("%s %s → %s", sensor.id, payload.hex().upper(), _summary(data))
                results.append(data)
        return results

    async def boot(self, sensor: VirtualSensor) -> list[dict]:
        return await self.send(
            sensor, encode_boot(sensor.next_counter(), battery_pct=sensor.battery)
        )

    async def heartbeat(self, sensor: VirtualSensor) -> list[dict]:
        if sensor.silent:
            return []
        if sensor.id in self.drain:
            sensor.battery = max(0, sensor.battery - 5)
        payload = encode_heartbeat(
            sensor.next_counter(),
            battery_pct=sensor.battery,
            rejected_events=self.rng.randint(0, 3),
            low_battery=sensor.battery < 20,
        )
        return await self.send(sensor, payload)

    async def alarm(
        self, sensor: VirtualSensor, *, false_alarm: bool = False
    ) -> list[dict]:
        """ALARM wysłany 3 razy z odstępem, jak w firmware; backend scali je w jeden alarm."""
        if false_alarm:
            params = {
                "sources": ["vibration"],
                "confidence": self.rng.randint(40, 60),
                "duration_s": self.rng.randint(2, 15),
                "energy": self.rng.randint(20, 90),
            }
        else:
            params = {
                "sources": ["microphone", "vibration"],
                "confidence": self.rng.randint(80, 97),
                "duration_s": self.rng.randint(30, 600),
                "energy": self.rng.randint(140, 250),
            }
        results = []
        for i in range(3):
            if i:
                await asyncio.sleep(self.repeat_gap_s)
            payload = encode_alarm(
                sensor.next_counter(), battery_pct=sensor.battery, **params
            )
            results += await self.send(sensor, payload)
        return results

    async def tick(self, alarm_chance: float = 0.0) -> None:
        """Jeden obrót pętli: heartbeat z każdego czujnika, czasem kradzież."""
        for sensor in self.sensors:
            await self.heartbeat(sensor)
        if alarm_chance and self.rng.random() < alarm_chance:
            await self.alarm(
                self.rng.choice(
                    [s for s in self.sensors if not s.silent] or self.sensors
                )
            )


def _summary(data: dict) -> str:
    if data.get("status") == "duplicate":
        return "duplicate"
    if data.get("alarm_created"):
        return f"NOWY ALARM #{data['alarm_id']}"
    if data.get("alarm_id"):
        return f"powtórzenie alarmu #{data['alarm_id']}"
    if data.get("muted"):
        return "alarm pominięty (wyciszony/wyłączony)"
    return "zapisano"


def load_state(path: Path, ids: list[str]) -> list[VirtualSensor]:
    saved = {}
    if path.exists():
        try:
            saved = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            log.warning("Nie da się odczytać %s, zaczynam od zera", path)
    return [
        VirtualSensor(**saved[i])
        if i in saved
        else VirtualSensor(id=i, battery=START_BATTERY.get(i, 95))
        for i in ids
    ]


def save_state(path: Path, sensors: list[VirtualSensor]) -> None:
    try:
        path.write_text(json.dumps({s.id: asdict(s) for s in sensors}, indent=2))
    except OSError as e:
        log.warning("Nie zapisano stanu do %s: %s", path, e)


async def wait_for_api(
    client: httpx.AsyncClient, timeout_s: float = 60, step_s: float = 2
) -> bool:
    """Czeka, aż backend odpowie na /health (w Dockerze startuje chwilę po kontenerze)."""
    waited = 0.0
    while True:
        try:
            if (await client.get("/health")).status_code == 200:
                return True
        except httpx.TransportError:
            pass
        if waited >= timeout_s:
            log.error("Backend nie odpowiada od %.0f s, kończę.", waited)
            return False
        if waited == 0:
            log.info("Czekam na backend...")
        await asyncio.sleep(step_s)
        waited += step_s


async def run(args: argparse.Namespace, client: httpx.AsyncClient) -> None:
    state_path = Path(args.state)
    if not await wait_for_api(client, timeout_s=args.wait):
        return
    sensors = load_state(state_path, args.sensors)
    for s in sensors:
        s.silent = False  # cisza dotyczy tylko jednego uruchomienia
    target = next((s for s in sensors if s.id == args.target), sensors[0])
    sim = Simulator(
        client,
        sensors,
        rng=random.Random(args.seed),
        repeat_gap_s=args.repeat_gap,
        duplicate=args.scenario == "duplicate",
    )
    log.info(
        "Czujniki: %s, scenariusz: %s (cel: %s)", len(sensors), args.scenario, target.id
    )

    try:
        for s in sensors:
            await sim.boot(s)
        if args.scenario == "theft":
            await sim.alarm(target)
        elif args.scenario == "false-alarm":
            await sim.alarm(target, false_alarm=True)
        elif args.scenario == "battery-drain":
            sim.drain.add(target.id)
        elif args.scenario == "silent":
            target.silent = True
            log.info("%s milknie", target.id)

        chance = args.alarm_chance if args.scenario == "normal" else 0.0
        while True:
            await sim.tick(alarm_chance=chance)
            save_state(state_path, sensors)
            if args.once:
                break
            await asyncio.sleep(args.interval)
    finally:
        save_state(state_path, sensors)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Symulator wirtualnych czujników")
    p.add_argument("--api", default="http://localhost:8000", help="adres backendu")
    p.add_argument(
        "--sensors",
        type=lambda v: [x.strip().upper() for x in v.split(",") if x.strip()],
        default=DEFAULT_SENSORS,
        help="ID czujników po przecinku (domyślnie czujniki z seed --demo)",
    )
    p.add_argument("--scenario", choices=SCENARIOS, default="normal")
    p.add_argument(
        "--target", type=str.upper, help="czujnik scenariusza (domyślnie pierwszy)"
    )
    p.add_argument(
        "--interval", type=float, default=30, help="sekundy między heartbeatami"
    )
    p.add_argument(
        "--repeat-gap", type=float, default=5, help="sekundy między powtórzeniami ALARM"
    )
    p.add_argument(
        "--alarm-chance",
        type=float,
        default=0.02,
        help="szansa kradzieży na obrót (normal)",
    )
    p.add_argument("--state", default=".simulator-state.json", help="plik z licznikami")
    p.add_argument("--seed", type=int, help="ziarno losowania (powtarzalne przebiegi)")
    p.add_argument("--once", action="store_true", help="jeden obrót i koniec")
    p.add_argument(
        "--wait", type=float, default=60, help="ile sekund czekać na start backendu"
    )
    return p.parse_args(argv)


async def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S"
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    async with httpx.AsyncClient(base_url=args.api, timeout=10) as client:
        await run(args, client)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nKoniec symulacji.")
