"""Formats publics et unicité persistante des nouveaux identifiants."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import os
import subprocess
import sys
import pytest
from pydantic import TypeAdapter
from greenmind.identifiers import next_id, next_simulation, ControlId
from greenmind.time_formats import local_text, parse_local


def test_counter_is_atomic_and_survives_another_process():
    with ThreadPoolExecutor(max_workers=8) as pool:
        ids = list(pool.map(lambda _: next_id('event'), range(40)))
    assert len(set(ids)) == 40
    assert 'Evenement_000001' in ids and 'Evenement_000040' in ids
    env = dict(os.environ, PYTHONPATH='src')
    value = subprocess.check_output([sys.executable, '-c',
        'from greenmind.identifiers import next_id; print(next_id("event"))'], env=env, text=True).strip()
    assert value == 'Evenement_000041'
    assert next_id('control') == 'Controle_000001'


def test_supplied_key_advances_allocator_without_increment_on_retry():
    adapter = TypeAdapter(ControlId)
    assert adapter.validate_python('Controle_000050') == 'Controle_000050'
    adapter.validate_python('Controle_000050')
    assert next_id('control') == 'Controle_000051'
    with pytest.raises(ValueError):
        adapter.validate_python('a1b2c3')


def test_simulation_label_belgian_time_and_persistent_counter():
    now = datetime(2026, 10, 28, 13, 30, 59, tzinfo=timezone.utc)
    assert next_simulation(now) == 'Simu_001 du 28 Oct. 2026 à 14:30'
    assert next_simulation(now) == 'Simu_002 du 28 Oct. 2026 à 14:30'


@pytest.mark.parametrize('month,hour', [(1, 13), (7, 14)])
def test_belgian_time_uses_summer_and_winter_offsets(month, hour):
    moment = datetime(2026, month, 10, 12, 15, 10, 123456, tzinfo=timezone.utc)
    label = f'2026-{month:02d}-10 {hour}:15:10.12345'
    assert local_text(moment) == label
    assert parse_local(label) == moment.replace(microsecond=123450)
    assert local_text(moment, False) == label.split('.')[0]


@pytest.mark.parametrize('value', ['2026-07-10T12:15:10Z', '2026-07-10 12:15:10.123456',
    '2026-03-29 02:30:00.12345', '2026-10-25 02:30:00.12345'])
def test_unapproved_or_ambiguous_dates_are_rejected(value):
    with pytest.raises(ValueError):
        parse_local(value)
