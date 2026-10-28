"""Application unique des arrosages, dans le thread du moteur MQTT."""

from dataclasses import dataclass
from datetime import datetime, timezone
from time import monotonic
from uuid import uuid4
from greenmind.greenhouse_config import GreenhouseConfig
from greenmind.schemas import WateringCommand, WateringEvent, telemetry_for_snapshot
from greenmind.simulator.engine import SimulationEngine


@dataclass(frozen=True)
class WateringResult:
    event: WateringEvent
    telemetry: tuple


class WateringProcessor:
    def __init__(self, engine: SimulationEngine, config: GreenhouseConfig, *, clock=monotonic):
        self.engine, self.config, self.clock = engine, config, clock
        self._results = {}
        self._last_watering = {}

    def apply(self, command: WateringCommand, now=None) -> WateringResult:
        now = now or datetime.now(timezone.utc)
        signature = command.model_dump_json()
        cached = self._results.get(command.command_id)
        if cached and cached[0] == signature:
            return cached[1]
        state = self.engine.snapshot()
        reason = None
        if cached:
            reason = "Identifiant d'arrosage réutilisé avec un contenu différent."
        elif len(self._results) >= 1000:
            reason = "Limite d'arrosages atteinte ; redémarrage contrôlé nécessaire."
        elif command.run_id != state.run_id:
            reason = "La commande vise une ancienne exécution."
        elif not command.requested_at <= now < command.expires_at:
            reason = "La commande est expirée ou sa date de demande est future."
        elif command.expected_revision != state.state_revision:
            reason = "La révision attendue n'est plus courante."
        profile = self.config.get_plant(command.plant_id)
        clock_now = self.clock()
        last = self._last_watering.get(command.plant_id)
        if reason is None and last is not None and clock_now - last < profile.watering_cooldown_real_s:
            reason = "Le bac est encore dans son délai de repos réel."
        messages = ()
        if reason is None:
            try:
                self.engine.water(command.plant_id, command.duration_sim_s)
                self._last_watering[command.plant_id] = clock_now
                messages = tuple(
                    m.model_copy(update={'measurement_origin': 'watering'})
                    if m.plant_id == command.plant_id else m
                    for m in telemetry_for_snapshot(self.engine.snapshot(), 'heartbeat')
                )
            except ValueError as error:
                reason = str(error)
        state = self.engine.snapshot()
        event = WateringEvent(
            event_id=uuid4(), command_id=command.command_id, run_id=state.run_id,
            plant_id=command.plant_id, actuator_id=command.actuator_id,
            status='REJECTED' if reason else 'APPLIED', resulting_revision=state.state_revision,
            simulated_at=state.simulated_at, emitted_at=now,
            soil_moisture_after_pct=state.soil[command.plant_id],
            duration_applied_sim_s=0.0 if reason else command.duration_sim_s,
            reason=reason or f"Arrosage virtuel exécuté sur {profile.display_name}.",
        )
        result = WateringResult(event, messages)
        if not cached and len(self._results) < 1000:
            self._results[command.command_id] = (signature, result)
        return result
