"""Les deux vues restent consultables et pilotent les routes REST."""
from io import BytesIO
import json
from pathlib import Path
from streamlit.testing.v1 import AppTest


def test_two_dashboard_views(monkeypatch):
    calls = []
    def response(request, **kwargs):
        calls.append((request.full_url, json.loads(request.data) if request.data else None))
        path = request.full_url.split('/api/v1')[1]
        value = []
        if path == '/simulation':
            value = dict(simulated_at='2026-07-10T00:00:00Z', heure_virtuelle=0, current_state=0, paused=True)
        elif path == '/identifiers/control':
            value = {'identifier': 'Controle_000001'}
        elif path.startswith('/simulation/controls'):
            value = {'control_id': 'Controle_000001', 'status': 'en_attente'}
        elif path == '/plants':
            value = [dict(plant_id=p, display_name=p, soil_moisture_pct=40, has_active_alert=False) for p in ['basilic', 'thym', 'romarin']]
        return BytesIO(json.dumps(value).encode())
    monkeypatch.setattr('urllib.request.urlopen', response)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'src/greenmind/dashboard/app.py'), default_timeout=30).run()
    assert not app.exception
    assert len(app.metric) == 3
    app.sidebar.radio[0].set_value('Console').run()
    assert not app.exception
    assert app.slider[0].value == 18.0

    next(b for b in app.button if b.label == 'Avancer d’une heure').click().run()
    assert not app.exception
    request = next(body for url, body in calls if url.endswith('/simulation/controls'))
    assert request == {'control_id': 'Controle_000001', 'action': 'avancer_1_heure', 'expected_state': 0}
