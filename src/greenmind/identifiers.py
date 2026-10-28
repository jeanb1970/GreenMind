"""Identifiants lisibles, alloués atomiquement entre processus et redémarrages."""
import os
from pathlib import Path
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Annotated
from pydantic import StringConstraints

PREFIXES = {'event': 'Evenement', 'control': 'Controle', 'command': 'Arrosage',
            'proposal': 'Proposition', 'alert': 'Alerte'}
EventId = Annotated[str, StringConstraints(pattern=r'^Evenement_[0-9]{6,}$')]
ControlId = Annotated[str, StringConstraints(pattern=r'^Controle_[0-9]{6,}$')]
CommandId = Annotated[str, StringConstraints(pattern=r'^Arrosage_[0-9]{6,}$')]
ProposalId = Annotated[str, StringConstraints(pattern=r'^Proposition_[0-9]{6,}$')]
SimulationId = Annotated[str, StringConstraints(pattern=r'^Simu_[0-9]{3,} du [0-9]{2} .+ [0-9]{4} à [0-9]{2}:[0-9]{2}$')]
MONTHS = ('Jan.', 'Fév.', 'Mars', 'Avr.', 'Mai', 'Juin', 'Juil.', 'Août', 'Sept.', 'Oct.', 'Nov.', 'Déc.')


def counter_path():
    return Path(os.environ.get('GREENMIND_IDENTIFIERS_PATH',
        str(Path(__file__).resolve().parents[2] / 'outputs/identifiers.sqlite'))).resolve()


def next_number(category):
    path = counter_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path, timeout=10) as db:
        db.execute('CREATE TABLE IF NOT EXISTS counters (category TEXT PRIMARY KEY, value INTEGER NOT NULL)')
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('INSERT INTO counters VALUES (?, 1) ON CONFLICT(category) DO UPDATE SET value=value+1 RETURNING value', (category,)).fetchone()
        return row[0]


def next_id(category):
    return f'{PREFIXES[category]}_{next_number(category):06d}'


def next_simulation(now=None):
    moment = (now or datetime.now(ZoneInfo('Europe/Brussels'))).astimezone(ZoneInfo('Europe/Brussels'))
    return (f'Simu_{next_number("simulation"):03d} du {moment.day:02d} '
            f'{MONTHS[moment.month-1]} {moment.year} à {moment:%H:%M}')


def observe_id(category, value):
    """Évite qu'une clé fournie par un client soit réallouée plus tard."""
    number = int(value.split('_', 1)[1]) if category != 'simulation' else int(value.split('_', 1)[1].split(' ', 1)[0])
    path = counter_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path, timeout=10) as db:
        db.execute('CREATE TABLE IF NOT EXISTS counters (category TEXT PRIMARY KEY, value INTEGER NOT NULL)')
        db.execute('INSERT INTO counters VALUES (?, ?) ON CONFLICT(category) DO UPDATE SET value=MAX(value, excluded.value)', (category, number))
    return value


from pydantic import AfterValidator
EventId = Annotated[EventId, AfterValidator(lambda v: observe_id('event', v))]
ControlId = Annotated[ControlId, AfterValidator(lambda v: observe_id('control', v))]
CommandId = Annotated[CommandId, AfterValidator(lambda v: observe_id('command', v))]
ProposalId = Annotated[ProposalId, AfterValidator(lambda v: observe_id('proposal', v))]
SimulationId = Annotated[SimulationId, AfterValidator(lambda v: observe_id('simulation', v))]
