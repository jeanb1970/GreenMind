"""Tests des seuils et du cycle d'une alerte de sécheresse."""

import pytest

from greenmind.domain.alerts import next_dry_alert_state


@pytest.mark.parametrize(
    "moisture, initially_open, expected_open",
    [
        (34.9, False, True),
        (35.0, False, False),
        (37.5, False, False),
        (0.0, False, True),
        (35.0, True, True),
        (40.0, True, True),
        (40.1, True, False),
        (100.0, True, False),
    ],
)
def test_alert_thresholds(moisture, initially_open, expected_open):
    result = next_dry_alert_state(
        moisture,
        alert_open=initially_open,
        low_threshold_sim_pct=35.0,
        rearm_threshold_sim_pct=40.0,
    )

    assert result is expected_open, (
        f"État incorrect pour une humidité de {moisture} %, "
        f"avec une alerte initialement ouverte : {initially_open}."
    )


def test_alert_remains_open_until_rearm_then_can_open_again():
    measurements = [
        37.5, 35.0, 32.5, 30.0, 35.0, 39.0, 40.0, 42.0, 36.0, 34.0
    ]
    expected_states = [
        False, False, True, True, True, True, True, False, False, True
    ]

    alert_open = False
    actual_states = []

    for moisture in measurements:
        alert_open = next_dry_alert_state(
            moisture,
            alert_open=alert_open,
            low_threshold_sim_pct=35.0,
            rearm_threshold_sim_pct=40.0,
        )
        actual_states.append(alert_open)

    assert actual_states == expected_states, (
        "L'alerte doit rester ouverte jusqu'au dépassement de 40 %, "
        "puis pouvoir se rouvrir lors d'un nouvel épisode sous 35 %."
    )