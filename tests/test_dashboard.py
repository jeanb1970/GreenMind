"""Les deux vues restent consultables et pilotent les routes REST."""
from io import BytesIO
import json
from pathlib import Path
from streamlit.testing.v1 import AppTest
import pytest


def simulation_state(**changes):
    return dict(simulation='Simu_001 du 28 Oct. 2026 à 12:00',
                simulated_at='2026-07-10 00:00:00', heure_virtuelle=0,
                current_state=0, paused=True, presence=True, simulation_mode=True,
                day_complete=False, air_temperature_c=22.5, air_humidity_pct=60.1234,
                observed_at='2026-07-10 00:00:00', provenance='meteo_simulee') | changes


def plant_summaries():
    return [dict(plant_id=p, display_name=p.capitalize(), soil_moisture_pct=40,
                 has_active_alert=False, arroseur_id='arroseur_' + p, arroseur_active=False,
                 moist_low_pct=low, moist_rearm_pct=rearm, moist_high_pct=high,
                 moist_target_pct=target)
            for p, low, rearm, high, target in [('basilic', 35, 40, 65, 50),
                ('thym', 20, 25, 45, 35), ('romarin', 25, 30, 50, 40)]]


def test_two_dashboard_views(monkeypatch):
    calls = []
    def response(request, **kwargs):
        calls.append((request.full_url, json.loads(request.data) if request.data else None))
        path = request.full_url.split('/api/v1')[1]
        value = []
        if path == '/simulation':
            value = simulation_state()
        elif path == '/identifiers/control':
            value = {'identifier': 'Controle_000001'}
        elif path.startswith('/simulation/controls'):
            value = {'control_id': 'Controle_000001', 'status': 'en_attente'}
        elif path == '/plants':
            value = plant_summaries()
        return BytesIO(json.dumps(value).encode())
    monkeypatch.setattr('urllib.request.urlopen', response)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'src/greenmind/dashboard/app.py'), default_timeout=30).run()
    assert not app.exception
    assert len(app.metric) == 5
    assert any(m.label == 'Température de l’air' and m.value == '22,50 °C' for m in app.metric)
    assert any(m.label == 'Humidité de l’air' and m.value == '60,12 %' for m in app.metric)
    assert any('Journée synthétique illustrative' in c.value for c in app.caption)
    assert all(any('Arroseur : arroseur_' + p in c.value for c in app.caption)
               for p in ['basilic', 'thym', 'romarin'])
    assert any('Seuil bas : 35,00 %' in c.value for c in app.caption)
    assert any('Cible d’arrosage : 50,00 %' in c.value for c in app.caption)
    assert any('pause et connectée' in info.value for info in app.info)
    assert app.title[0].value == 'Serre'
    assert app.session_state['appearance'] == 'Clair'
    app.session_state['appearance'] = 'Sombre'
    app.run()
    assert all(m.value == '40,00 %' for m in app.metric if m.label == 'Humidité du sol')
    app.sidebar.radio[0].set_value('Console').run()
    assert not app.exception
    assert app.slider[0].value == 18.0
    assert app.title[0].value == 'Console · Mode simulation'
    assert app.session_state['appearance'] == 'Sombre'

    next(b for b in app.button if b.label == 'Avancer d’une heure').click().run()
    assert not app.exception
    request = next(body for url, body in calls if url.endswith('/simulation/controls'))
    assert request == {'control_id': 'Controle_000001', 'action': 'avancer_1_heure', 'expected_state': 0}


def test_assistant_shows_facts_explanation_and_local_excerpt(monkeypatch):
    from greenmind.rag.corpus import load_corpus
    passage = next(p for p in load_corpus() if p.plant_id == 'basilic')
    calls = []
    def response(request, **kwargs):
        path = request.full_url.split('/api/v1')[1]
        calls.append(path)
        if path == '/simulation':
            result = simulation_state()
        elif path == '/plants':
            result = [dict(plant_id='basilic', display_name='Basilic', soil_moisture_pct=32, has_active_alert=True)]
        elif path == '/assistant/ask':
            result = dict(plant_id='basilic', status='répondu', facts={'soil_moisture_pct': 32, 'fresh': True},
                          explanation='Le substrat en pot sèche plus vite.', sources=[{**passage.citation(), 'citation_id': 'S1'}])
        else:
            result = []
        return BytesIO(json.dumps(result).encode())
    monkeypatch.setattr('urllib.request.urlopen', response)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'src/greenmind/dashboard/app.py'), default_timeout=30).run()
    app.text_input[0].set_value('Pourquoi son sol se dessèche ?')
    next(b for b in app.button if b.label == 'Poser la question').click().run()
    assert not app.exception
    assert '/assistant/ask' in calls
    assert any('Le substrat en pot' in m.value for m in app.markdown)
    assert any('Besoins en eau' in e.label for e in app.expander)


def test_common_chart_preserves_virtual_hours_and_interventions():
    from greenmind.dashboard.charts import moisture_chart
    rows = [dict(plant_id=p, event_id=f'Evenement_{revision:06}',
                 emitted_at='2026-10-28 12:00:00.00000',
                 heure_virtuelle=hour, current_state=revision,
                 soil_moisture_pct=moisture, measurement_origin=origin)
            for p in ['basilic', 'thym', 'romarin']
            for revision, hour, moisture, origin in [
                (0, 0, 50.12345, 'initial'), (1, 1, 45.0, 'calcul_horaire'),
                (2, 1, 32.0, 'modification_manuelle'), (3, 1, 50.0, 'arrosage')]]
    chart = moisture_chart(list(reversed(rows))).to_dict()
    data = chart['data']['values']
    basilic = [r for r in data if r['plant_id'] == 'basilic']
    assert [r['heure_virtuelle'] for r in basilic] == [0, 1, 1, 1]
    assert [r['soil_moisture_pct'] for r in basilic] == [50.12345, 45, 32, 50]
    assert basilic[0]['humidite'] == '50,12 %'
    assert chart['encoding']['y']['scale']['domain'] == [0, 100]
    assert chart['encoding']['color']['scale']['domain'] == ['Basilic', 'Thym', 'Romarin']
    assert chart['mark']['point'] is True


@pytest.mark.parametrize('changes, message', [
    ({'simulation': None}, 'Aucune simulation initialisée'),
    ({'simulated_at': None}, 'aucune mesure de référence'),
    ({'presence': False}, 'aucun signal de présence récent'),
    ({'presence': False, 'paused': False}, 'aucun signal de présence récent'),
])
def test_dashboard_does_not_call_missing_simulator_paused(monkeypatch, changes, message):
    state = simulation_state(**changes)
    def response(request, **kwargs):
        path = request.full_url.split('/api/v1')[1]
        result = state if path == '/simulation' else plant_summaries() if path == '/plants' else []
        return BytesIO(json.dumps(result).encode())
    monkeypatch.setattr('urllib.request.urlopen', response)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'src/greenmind/dashboard/app.py')).run()
    assert not app.exception
    assert any(message in warning.value for warning in app.warning)
    assert not any('pause et connectée' in item.value or 'lecture et connectée' in item.value for item in app.info)
    assert all(b.disabled for b in app.button if b.label == 'Proposer un arrosage')
    app.sidebar.radio[0].set_value('Console').run()
    assert not app.exception
    assert all(b.disabled for b in app.button if b.label in
               ['Pause', 'Reprendre', 'Avancer d’une heure', 'Imposer cette humidité'])


def test_console_disabled_mode_preserves_consultation(monkeypatch):
    calls = []
    def response(request, **kwargs):
        path = request.full_url.split('/api/v1')[1]
        calls.append(path)
        result = simulation_state(simulation_mode=False) if path == '/simulation' else []
        return BytesIO(json.dumps(result).encode())
    monkeypatch.setattr('urllib.request.urlopen', response)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'src/greenmind/dashboard/app.py')).run()
    app.sidebar.radio[0].set_value('Console').run()
    assert not app.exception
    assert any('Mode simulation désactivé' in item.value for item in app.info)
    assert all(b.disabled for b in app.button if b.label in
               ['Pause', 'Reprendre', 'Avancer d’une heure', 'Imposer cette humidité'])
    assert not any('/identifiers' in path or '/simulation/controls' in path for path in calls)


def test_next_day_button_uses_current_revision(monkeypatch):
    calls = []
    def response(request, **kwargs):
        path = request.full_url.split('/api/v1')[1]
        if request.data:
            calls.append((path, json.loads(request.data)))
        value = []
        if path == '/simulation':
            value = simulation_state(cycle=2, heure_virtuelle=24, day_complete=True, current_state=51)
        elif path == '/identifiers/control':
            value = {'identifier': 'Controle_000001'}
        elif path == '/simulation/controls':
            value = {'control_id': 'Controle_000001'}
        return BytesIO(json.dumps(value).encode())
    monkeypatch.setattr('urllib.request.urlopen', response)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'src/greenmind/dashboard/app.py')).run()
    app.sidebar.radio[0].set_value('Console').run()
    assert not next(b for b in app.button if b.label == 'Jour suivant').disabled
    assert next(b for b in app.button if b.label == 'Reprendre').disabled
    next(b for b in app.button if b.label == 'Jour suivant').click().run()
    assert ('/simulation/controls', {'control_id': 'Controle_000001', 'action': 'jour_suivant', 'expected_state': 51}) in calls
    assert not app.exception


def test_assistant_unavailable_is_visible_before_question(monkeypatch):
    calls = []
    def response(request, **kwargs):
        path = request.full_url.split('/api/v1')[1]
        calls.append(path)
        value = []
        if path == '/simulation':
            value = simulation_state()
        elif path == '/assistant/health':
            value = dict(available=False, status='indisponible', reason='Ollama ne répond pas.')
        return BytesIO(json.dumps(value).encode())
    monkeypatch.setattr('urllib.request.urlopen', response)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'src/greenmind/dashboard/app.py')).run()
    assert any('Ollama ne répond pas' in warning.value for warning in app.warning)
    assert '/assistant/ask' not in calls
    assert not app.exception
