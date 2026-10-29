"""B8 : faits exacts, sources contrôlées, pas d'action et génération bornée."""
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import pytest
import httpx2 as httpx
from fastapi.testclient import TestClient
from greenmind.api.app import create_app
from greenmind.api.assistant import get_assistant
from greenmind.api.dependencies import get_db, get_config, get_publisher
from greenmind.db.models import Base
from greenmind.db.readings import save_message
from greenmind.db.session import create_database_engine
from greenmind.greenhouse_config import load_greenhouse_config
from greenmind.rag.assistant import Assistant
from greenmind.rag.corpus import load_corpus
from greenmind.identifiers import next_simulation, next_id
from greenmind.schemas import TelemetryV3

ROOT = Path(__file__).resolve().parents[1]


def matches(question, plant):
    return [{**p.citation(), 'score': 0.8} for p in load_corpus() if p.plant_id == plant]


def llm_response(explanation='Le substrat drainant permet à l’eau de s’évacuer.', sources=None, sufficient=True):
    return {'done': True, 'message': {'content': json.dumps(dict(
        explanation=explanation, source_ids=['S2'] if sources is None else sources, sufficient=sufficient))}}


@pytest.fixture
def setup(tmp_path):
    db = create_database_engine(tmp_path / 'assistant.sqlite')
    config = load_greenhouse_config(ROOT / 'config/greenhouse.yaml')
    simulation = next_simulation()
    now = datetime.now(timezone.utc)
    virtual = datetime(2026, 7, 9, 22, tzinfo=timezone.utc)
    for plant in ('basilic', 'thym', 'romarin'):
        save_message(db, TelemetryV3(event_id=next_id('event'), simulation=simulation, plant_id=plant,
            observed_at=virtual, simulated_at=virtual, emitted_at=now, heure_virtuelle=0,
            current_state=1, paused=True, day_complete=False, air_temperature_c=22.0,
            air_humidity_pct=60.0, soil_moisture_pct=18.0 if plant == 'thym' else 40.0,
            arroseur_active=False, provenance='meteo_simulee', measurement_origin='modification_manuelle'))
    yield db, config
    db.dispose()


def api_client(setup, assistant):
    db, config = setup
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_config] = lambda: config
    app.dependency_overrides[get_assistant] = lambda: assistant
    def forbidden(): raise AssertionError('Le chat ne doit jamais demander un producteur MQTT.')
    app.dependency_overrides[get_publisher] = forbidden
    return TestClient(app)


@pytest.mark.parametrize('plant', ['basilic', 'thym', 'romarin'])
def test_real_facts_and_citations_are_server_owned(setup, plant):
    calls = []
    class Service:
        async def explain(self, *args):
            def handler(request):
                calls.append(json.loads(request.content))
                return httpx.Response(200, json=llm_response())
            async with httpx.AsyncClient(base_url='http://ollama.test', transport=httpx.MockTransport(handler)) as http:
                return await Assistant(http, search=matches).explain(*args)
    client = api_client(setup, Service())
    result = client.post('/api/v1/assistant/ask', json={'plant_id': plant, 'question': 'Pourquoi le drainage est-il important en pot ?'})
    assert result.status_code == 200
    data = result.json()
    assert data['status'] == 'répondu' and data['action_executed'] is False
    assert data['facts']['soil_moisture_pct'] == (18.0 if plant == 'thym' else 40.0)
    assert data['facts']['measurement_origin'] == 'modification_manuelle'
    assert data['facts']['has_active_alert'] == (plant == 'thym')
    assert all(s['plant_id'] == plant and s['citation_id'] == 'S2' for s in data['sources'])
    assert data['sources'][0]['excerpt'] in (ROOT / data['sources'][0]['local_path']).read_text()
    assert 'tools' not in calls[0]
    assert calls[0]['stream'] is False and calls[0]['think'] is False
    assert calls[0]['options']['num_predict'] == 500


@pytest.mark.parametrize('question,status', [
    ('Arrose le thym maintenant', 'action_non_exécutée'),
    ('Quel diagnostic certain de maladie ?', 'sources_insuffisantes'),
    ('Quel est le cours du bitcoin ?', 'sources_insuffisantes'),
    ('Compare les besoins en eau du basilic et du thym', 'sources_insuffisantes'),
])
def test_unsupported_or_action_requests_never_reach_llm(setup, question, status):
    class Service:
        async def explain(self, *args):
            def forbidden(request): raise AssertionError('Pas de génération nécessaire')
            async with httpx.AsyncClient(transport=httpx.MockTransport(forbidden)) as http:
                return await Assistant(http, search=matches).explain(*args)
    db, _ = setup
    with db.connect() as connection:
        before = {t.name: connection.exec_driver_sql(f'SELECT COUNT(*) FROM {t.name}').scalar() for t in Base.metadata.sorted_tables}
    result = api_client(setup, Service()).post('/api/v1/assistant/ask', json={'plant_id': 'thym', 'question': question}).json()
    assert result['status'] == status and not result['action_executed']
    with db.connect() as connection:
        after = {t.name: connection.exec_driver_sql(f'SELECT COUNT(*) FROM {t.name}').scalar() for t in Base.metadata.sorted_tables}
    assert before == after


@pytest.mark.parametrize('generated', [llm_response(explanation='Le sol est à 99 %.'), llm_response(sources=['S99']),
    llm_response(explanation='Voir https://inventee.example'), llm_response(explanation="J’ai arrosé le bac."), llm_response(explanation='Le substrat doit rester sec.'),
    {'done': True, 'message': {'content': 'texte sans JSON'}},
    {'done': False, 'message': {'content': ''}}, [],
    {'done': True, 'message': {'content': '{}', 'tool_calls': [{'name': 'arroser'}]}}])
def test_invented_numbers_sources_and_execution_claims_are_rejected(generated):
    async def run():
        async with httpx.AsyncClient(base_url='http://ollama.test', transport=httpx.MockTransport(lambda r: httpx.Response(200, json=generated))) as http:
            result = await Assistant(http, search=matches).explain('Pourquoi le drainage ?', 'thym', {})
            assert result['status'] == 'indisponible' and not result['sources']
    asyncio.run(run())


def test_llm_can_report_insufficient_sources():
    async def run():
        async with httpx.AsyncClient(base_url='http://ollama.test', transport=httpx.MockTransport(lambda r: httpx.Response(200, json=llm_response(sources=[], sufficient=False)))) as http:
            result = await Assistant(http, search=matches).explain('Quelle eau pour ce bac ?', 'basilic', {})
            assert result['status'] == 'sources_insuffisantes'
    asyncio.run(run())


def test_busy_and_deadline_do_not_block_another_task():
    async def run():
        entered = asyncio.Event()
        release = asyncio.Event()
        async def handler(request):
            entered.set()
            await release.wait()
            return httpx.Response(200, json=llm_response())
        async with httpx.AsyncClient(base_url='http://ollama.test', transport=httpx.MockTransport(handler)) as http:
            service = Assistant(http, search=matches, timeout_s=0.1)
            first = asyncio.create_task(service.explain('Pourquoi le drainage ?', 'thym', {}))
            await entered.wait()
            second = await service.explain('Pourquoi ce substrat ?', 'basilic', {})
            assert second['status'] == 'occupé'
            # Une autre tâche reste exécutable pendant la génération.
            assert await asyncio.sleep(0, result='IoT disponible') == 'IoT disponible'
            assert (await first)['status'] == 'indisponible'
            release.set()
            await service.close()
    asyncio.run(run())


def test_model_failure_still_returns_facts(setup):
    class Service:
        async def explain(self, *args):
            def unavailable(request): raise httpx.ConnectError('Ollama absent')
            async with httpx.AsyncClient(base_url='http://ollama.test', transport=httpx.MockTransport(unavailable)) as http:
                return await Assistant(http, search=matches).explain(*args)
    client = api_client(setup, Service())
    result = client.post('/api/v1/assistant/ask', json={'plant_id': 'thym', 'question': 'Pourquoi son sol est-il sec ?'})
    assert result.status_code == 200
    assert result.json()['status'] == 'indisponible'
    assert result.json()['facts']['soil_moisture_pct'] == 18.0
    assert client.get('/api/v1/plants').status_code == 200


def test_invalid_questions_and_missing_measurements(setup):
    class Service:
        async def explain(self, *args): raise AssertionError('Aucun appel attendu')
    client = api_client(setup, Service())
    for question in ('', '   ', 'x'*1001):
        assert client.post('/api/v1/assistant/ask', json={'plant_id': 'thym', 'question': question}).status_code == 422
    assert client.post('/api/v1/assistant/ask', json={'plant_id': 'inconnu', 'question': 'Eau ?'}).status_code == 404
    db, _ = setup
    with db.begin() as connection:
        connection.exec_driver_sql('DELETE FROM sensor_readings')
    result = client.post('/api/v1/assistant/ask', json={'plant_id': 'thym', 'question': 'Pourquoi son sol est-il sec ?'}).json()
    assert not result['facts']['measurement_available']


def test_lifespan_shares_client_and_closes_service(setup):
    db, config = setup
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_config] = lambda: config
    with TestClient(app) as client:
        service = client.app.state.assistant
        assert not service.client.is_closed
        assert client.get('/api/v1/plants').status_code == 200
    assert service.client.is_closed


def test_missing_index_and_low_similarity_do_not_generate():
    async def run():
        def forbidden(request): raise AssertionError('Pas de source valide : aucun appel LLM')
        async with httpx.AsyncClient(transport=httpx.MockTransport(forbidden)) as http:
            def missing(*args): raise ValueError('Corpus modifié')
            result = await Assistant(http, search=missing).explain('Pourquoi le drainage ?', 'thym', {})
            assert result['status'] == 'indisponible'
            result = await Assistant(http, search=lambda *args: []).explain('Pourquoi le drainage ?', 'thym', {})
            assert result['status'] == 'sources_insuffisantes'
    asyncio.run(run())


def test_timeout_does_not_allow_a_second_native_search():
    from threading import Event
    release = Event()
    started = Event()
    searches = []
    def slow_search(*args):
        searches.append(args)
        started.set()
        release.wait(2)
        return matches(*args)
    async def run():
        async with httpx.AsyncClient() as http:
            service = Assistant(http, search=slow_search, timeout_s=0.05)
            try:
                first = asyncio.create_task(service.explain('Pourquoi le drainage ?', 'thym', {}))
                while not started.is_set():
                    await asyncio.sleep(0.001)
                assert (await first)['status'] == 'indisponible'
                assert (await service.explain('Pourquoi le sol ?', 'basilic', {}))['status'] == 'occupé'
                assert len(searches) == 1
                release.set()
                await service._task
            finally:
                release.set()
                await service.close()
    asyncio.run(run())

@pytest.mark.parametrize('mode', ['ready', 'offline', 'missing', 'bad_index'])
def test_availability_without_generation(mode):
    async def scenario():
        calls = []
        def handler(request):
            calls.append(request.url.path)
            assert request.method == 'GET'
            if mode == 'offline':
                raise httpx.ConnectError('offline')
            return httpx.Response(200, json={'models': [] if mode == 'missing' else [{'name': 'qwen3:4b-instruct'}]})
        def search(*args):
            if mode == 'bad_index':
                raise ValueError('invalid index')
            return matches(*args)
        async with httpx.AsyncClient(base_url='http://ollama.test', transport=httpx.MockTransport(handler)) as http:
            assistant = Assistant(http, search=search)
            result = await assistant.availability()
            if assistant._readiness_task is not None:
                await assistant._readiness_task
                result = await assistant.availability()
            assert result['available'] == (mode == 'ready')
            assert set(calls) == {'/api/tags'}
            await assistant.close()
    asyncio.run(scenario())
