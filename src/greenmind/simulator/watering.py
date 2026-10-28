"""Application unique des arrosages, dans le thread du moteur MQTT."""
from greenmind.identifiers import next_id

from dataclasses import dataclass
from datetime import datetime, timezone
from time import monotonic
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
        elif command.simulation != state.simulation:
            reason = "La commande vise une ancienne exécution."
        elif not command.requested_at <= now < command.expires_at:
            reason = "La commande est expirée ou sa date de demande est future."
        elif command.expected_state != state.current_state:
            reason = "La révision attendue n'est plus courante."
        profile = self.config.get_plant(command.plant_id)
        clock_now = self.clock()
        last = self._last_watering.get(command.plant_id)
        if reason is None and last is not None and clock_now - last < profile.watering_rest_s:
            reason = "Le bac est encore dans son délai de repos réel."
        messages = ()
        if reason is None:
            try:
                self.engine.water(command.plant_id, command.watering_duration_s)
                self._last_watering[command.plant_id] = clock_now
                messages = tuple(
                    m.model_copy(update={'measurement_origin': 'arrosage'})
                    if m.plant_id == command.plant_id else m
                    for m in telemetry_for_snapshot(self.engine.snapshot(), 'signal_presence')
                )
            except ValueError as error:
                reason = str(error)
        state = self.engine.snapshot()
        event = WateringEvent(
            event_id=next_id("event"), command_id=command.command_id, simulation=state.simulation,
            plant_id=command.plant_id, arroseur_id=command.arroseur_id,
            status='refusé' if reason else 'appliqué', resulting_state=state.current_state,
            simulated_at=state.simulated_at, emitted_at=now,
            moist_after_pct=state.soil[command.plant_id],
            watering_applied_duration_s=0.0 if reason else command.watering_duration_s,
            reason=reason or f"Arrosage virtuel exécuté sur {profile.display_name}.",
        )
        result = WateringResult(event, messages)
        if not cached and len(self._results) < 1000:
            self._results[command.command_id] = (signature, result)
        return result
