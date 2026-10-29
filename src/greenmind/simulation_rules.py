"""Règles communes du scénario fixe, indépendantes des transports et du front."""
from typing import Literal

HOURS_PER_CYCLE = 24
PRESENCE_TTL_SECONDS = 10
MAX_MEASUREMENTS = 1000
MAX_JOURNAL_EVENTS = 100
SimulationAction = Literal[
    "pause", "reprendre", "avancer_1_heure", "jour_suivant", "modifier_humidite_sol",
]


def elapsed_hours(cycle: int, hour: int) -> int:
    """Position chronologique d'un pas, même si la date météo est rejouée."""
    return (cycle - 1) * HOURS_PER_CYCLE + hour


def is_connected(state) -> bool:
    """Une session stockée ne prouve pas à elle seule la présence du moteur."""
    return bool(state and state.get('simulation') and state.get('simulated_at') and state.get('presence'))
