"""Accès REST du front ; aucune lecture SQLite ni publication MQTT directe."""
import json
import os
import urllib.request
from urllib.request import Request
from urllib.error import HTTPError, URLError
import streamlit as st

def api(path, payload=None, timeout=5):
    data = None if payload is None else json.dumps(payload).encode()
    request = Request(os.environ.get('GREENMIND_API_URL', 'http://127.0.0.1:8000/api/v1') + path, data=data, headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except HTTPError as error:
        st.error(f'Action refusée : {error.read().decode()}')
    except (URLError, TimeoutError):
        st.error('API indisponible. Vérifiez les services GreenMind.')
    return None



def request_control(action, state, **arguments):
    key = api('/identifiers/control', {})
    if key:
        return api('/simulation/controls', {
            'control_id': key['identifier'], 'action': action,
            'expected_state': state['current_state'], **arguments,
        })
    return None


