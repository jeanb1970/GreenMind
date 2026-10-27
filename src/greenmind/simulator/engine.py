"""Moteur local v1.4 : journée horaire, pause et interventions explicites.

L'appelant sérialise les appels et transporte les transitions vers MQTT en B3.
Ce module ne dort pas, ne publie pas et ne modifie aucune base.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from math import isfinite
from time import monotonic
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from greenmind.domain.greenhouse import dry_greenhouse_one_hour, initial_soil_state
from greenmind.greenhouse_config import GreenhouseConfig
from greenmind.simulator.weather import ALLOWED_PROVENANCES, WeatherReading


SCENARIO_TIMEZONE = ZoneInfo("Europe/Brussels")
REAL_SECONDS_PER_HOUR = 5.0


@dataclass(frozen=True)
class SimulationSnapshot:
    """Copie immuable d'un état ; la météo est celle du dernier pas appliqué."""

    run_id: UUID
    simulated_at: datetime
    simulated_tick: int
    state_revision: int
    paused: bool
    completed: bool
    weather: WeatherReading
    soil_values: tuple[tuple[str, float], ...]

    @property
    def soil(self) -> dict[str, float]:
        """Fournit une copie utilisable sans exposer l'état interne."""
        return dict(self.soil_values)


@dataclass(frozen=True)
class SimulationTransition:
    """Avant/après d'une mutation, destiné au futur journal et transport."""

    kind: str
    before: SimulationSnapshot
    after: SimulationSnapshot
    plant_id: str | None = None


def validate_weather_day(readings: Sequence[WeatherReading]) -> None:
    """Exige 24 intervalles consécutifs à partir de minuit du scénario."""
    if len(readings) != 24:
        raise ValueError("La journée de serre doit contenir exactement 24 heures.")
    start = readings[0].observed_at
    if start.tzinfo is None or start.utcoffset() is None:
        raise ValueError("La journée météo doit préciser son fuseau horaire.")
    start = start.astimezone(timezone.utc)
    local = start.astimezone(SCENARIO_TIMEZONE)
    if (local.hour, local.minute, local.second, local.microsecond) != (0, 0, 0, 0):
        raise ValueError("La journée météo doit commencer à minuit en Europe/Brussels.")
    end = (start + timedelta(hours=24)).astimezone(SCENARIO_TIMEZONE)
    if end.hour != 0 or end.date() != local.date() + timedelta(days=1):
        raise ValueError("Choisir une journée de 24 heures sans changement d'heure.")
    for index, reading in enumerate(readings):
        if reading.observed_at != start + timedelta(hours=index):
            raise ValueError("Les 24 heures météo doivent être consécutives sans lacune.")
        if not all(isfinite(v) for v in (
            reading.air_temperature_c, reading.air_humidity_pct,
        )) or not 0 <= reading.air_humidity_pct <= 100:
            raise ValueError("Les valeurs météo doivent être finies et l'humidité entre 0 et 100.")
        if reading.provenance not in ALLOWED_PROVENANCES:
            raise ValueError("La provenance météo doit être reconnue.")


class SimulationEngine:
    """Une exécution indépendante, initialement en pause au pas zéro."""

    def __init__(
        self,
        config: GreenhouseConfig,
        weather: Sequence[WeatherReading],
        *,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        validate_weather_day(weather)
        self._config = config
        self._weather = tuple(weather)
        self._clock = clock
        self._last_clock: float | None = None
        self._deadline: float | None = None
        self._run_id = uuid4()
        self._soil = initial_soil_state(config)
        self._tick = 0
        self._revision = 0
        self._paused = True

    def snapshot(self) -> SimulationSnapshot:
        return SimulationSnapshot(
            run_id=self._run_id,
            simulated_at=self._weather[0].observed_at + timedelta(hours=self._tick),
            simulated_tick=self._tick,
            state_revision=self._revision,
            paused=self._paused,
            completed=self._tick == len(self._weather),
            weather=self._weather[max(0, self._tick - 1)],
            soil_values=tuple(self._soil.items()),
        )

    def _now(self) -> float:
        now = self._clock()
        if not isfinite(now) or (self._last_clock is not None and now < self._last_clock):
            raise ValueError("L'horloge réelle doit être finie et monotone.")
        self._last_clock = now
        return now

    def resume(self) -> SimulationTransition | None:
        if self._tick == len(self._weather):
            raise ValueError("La journée est terminée ; démarrer une nouvelle exécution.")
        if not self._paused:
            return None
        deadline = self._now() + REAL_SECONDS_PER_HOUR
        before = self.snapshot()
        self._deadline = deadline
        self._paused = False
        self._revision += 1
        return SimulationTransition("resumed", before, self.snapshot())

    def pause(self) -> SimulationTransition | None:
        if self._paused:
            return None
        before = self.snapshot()
        self._paused = True
        self._deadline = None
        self._revision += 1
        return SimulationTransition("paused", before, self.snapshot())

    def advance_one_hour(self) -> SimulationTransition:
        if not self._paused:
            raise ValueError("Mettre la simulation en pause avant une avance manuelle.")
        return self._advance()

    def _advance(self) -> SimulationTransition:
        if self._tick == len(self._weather):
            raise ValueError("La journée est terminée ; aucune heure supplémentaire disponible.")
        before = self.snapshot()
        reading = self._weather[self._tick]
        soil = dry_greenhouse_one_hour(
            self._config, self._soil,
            reading.air_temperature_c, reading.air_humidity_pct,
        )
        self._soil = soil
        self._tick += 1
        self._revision += 1
        if self._tick == len(self._weather):
            self._paused = True
            self._deadline = None
        return SimulationTransition("hour_advanced", before, self.snapshot())

    def poll(self) -> SimulationTransition | None:
        """Applique au plus une heure échue, sans rafale de rattrapage.

        Un appel retardé ne saute aucune ligne météo. Le prochain pas attendra
        cinq secondes après cet appel ; le temps réel total peut donc s'allonger.
        En pause, un appel sert seulement à constater l'absence de progression.
        """
        if self._paused:
            return None
        now = self._now()
        if self._deadline is None or now < self._deadline:
            return None
        result = self._advance()
        if not self._paused:
            self._deadline = now + REAL_SECONDS_PER_HOUR
        return result

    def set_soil_moisture(self, plant_id: str, value: float) -> SimulationTransition:
        if not self._paused:
            raise ValueError("Mettre la simulation en pause avant de modifier l'humidité.")
        self._config.get_plant(plant_id)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("L'humidité imposée doit être un nombre entre 0 et 100.")
        if not isfinite(value) or not 0 <= value <= 100:
            raise ValueError("L'humidité imposée doit être finie et entre 0 et 100.")
        before = self.snapshot()
        self._soil = {**self._soil, plant_id: float(value)}
        self._revision += 1
        return SimulationTransition("manual_override", before, self.snapshot(), plant_id)
