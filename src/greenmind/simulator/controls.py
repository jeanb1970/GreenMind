"""Contrôles sérialisés et idempotents dans une session du simulateur."""
from greenmind.identifiers import next_id
from dataclasses import dataclass
from datetime import datetime, timezone
from greenmind.schemas import SimulationControl, SimulationEvent, telemetry_for_snapshot
from greenmind.simulator.engine import SimulationEngine

@dataclass(frozen=True)
class ControlResult:
    event: SimulationEvent
    telemetry: tuple

class ControlProcessor:
    def __init__(self, engine: SimulationEngine):
        self.engine = engine
        self._results = {}

    def state_event(self):
        state = self.engine.snapshot()
        return SimulationEvent(
            event_id=next_id("event"), simulation=state.simulation, status="etat_actuel",
            cycle=state.cycle, current_state=state.current_state, heure_virtuelle=state.heure_virtuelle,
            simulated_at=state.simulated_at, emitted_at=datetime.now(timezone.utc),
            paused=state.paused, day_complete=state.day_complete, reason="État courant du simulateur.",
        )

    def apply(self, control: SimulationControl, now=None):
        now = now or datetime.now(timezone.utc)
        signature = control.model_dump_json()
        cached = self._results.get(control.control_id)
        if cached and cached[0] == signature:
            return cached[1]
        reason = None
        state = self.engine.snapshot()
        if cached:
            reason = "Identifiant de contrôle réutilisé avec un contenu différent."
        elif len(self._results) >= 1000:
            reason = "Limite de contrôles atteinte ; redémarrage contrôlé nécessaire."
        elif control.simulation != state.simulation:
            reason = "Le contrôle appartient à une autre exécution."
        elif not control.requested_at <= now < control.expires_at:
            reason = "Le contrôle est expiré ou sa date de demande est future."
        elif control.expected_state != state.current_state:
            reason = "La révision attendue n'est plus courante."
        messages = ()
        if reason is None:
            try:
                if control.action == "pause":
                    self.engine.pause()
                elif control.action == "reprendre":
                    self.engine.resume()
                elif control.action == "avancer_1_heure":
                    self.engine.advance_one_hour()
                elif control.action == "jour_suivant":
                    self.engine.next_day()
                else:
                    self.engine.set_soil_moisture(control.plant_id, control.moist_request_pct)
                origin = "calcul_horaire" if control.action == "avancer_1_heure" else "signal_presence"
                if control.action == "jour_suivant":
                    origin = "jour_suivant"
                messages = telemetry_for_snapshot(self.engine.snapshot(), origin)
                if control.action == "modifier_humidite_sol":
                    messages = tuple(m.model_copy(update={"measurement_origin": "modification_manuelle"})
                                     if m.plant_id == control.plant_id else m for m in messages)
            except ValueError as error:
                reason = str(error)
        event = self.state_event().model_copy(update={
            "control_id": control.control_id, "status": "refusé" if reason else "appliqué",
            "reason": reason or "Contrôle appliqué par le simulateur.",
        })
        result = ControlResult(event, messages)
        if not cached and len(self._results) < 1000:
            self._results[control.control_id] = (signature, result)
        return result
