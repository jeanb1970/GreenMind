"""Contrôles sérialisés et idempotents dans une session du simulateur."""
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4
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
            event_id=uuid4(), run_id=state.run_id, status="STATE",
            state_revision=state.state_revision, simulated_tick=state.simulated_tick,
            simulated_at=state.simulated_at, emitted_at=datetime.now(timezone.utc),
            paused=state.paused, completed=state.completed, reason="État courant du simulateur.",
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
        elif control.run_id != state.run_id:
            reason = "Le contrôle appartient à une autre exécution."
        elif not control.requested_at <= now < control.expires_at:
            reason = "Le contrôle est expiré ou sa date de demande est future."
        elif control.expected_revision != state.state_revision:
            reason = "La révision attendue n'est plus courante."
        messages = ()
        if reason is None:
            try:
                if control.action == "PAUSE":
                    self.engine.pause()
                elif control.action == "RESUME":
                    self.engine.resume()
                elif control.action == "ADVANCE":
                    self.engine.advance_one_hour()
                else:
                    self.engine.set_soil_moisture(control.plant_id, control.value)
                origin = "model" if control.action == "ADVANCE" else "heartbeat"
                messages = telemetry_for_snapshot(self.engine.snapshot(), origin)
                if control.action == "SET_SOIL_MOISTURE":
                    messages = tuple(m.model_copy(update={"measurement_origin": "manual_override"})
                                     if m.plant_id == control.plant_id else m for m in messages)
            except ValueError as error:
                reason = str(error)
        event = self.state_event().model_copy(update={
            "control_id": control.control_id, "status": "REJECTED" if reason else "APPLIED",
            "reason": reason or "Contrôle appliqué par le simulateur.",
        })
        result = ControlResult(event, messages)
        if not cached and len(self._results) < 1000:
            self._results[control.control_id] = (signature, result)
        return result
