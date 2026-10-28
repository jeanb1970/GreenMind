"""Interface locale de la serre ; toutes les actions passent par REST."""
import json
import os
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import streamlit as st

BASE = os.environ.get('GREENMIND_API_URL', 'http://127.0.0.1:8000/api/v1')
st.set_page_config(page_title='GreenMind', page_icon='🌱', layout='wide')


def api(path, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    request = Request(BASE + path, data=data, headers={'Content-Type': 'application/json'})
    try:
        with urlopen(request, timeout=5) as response:
            return json.load(response)
    except HTTPError as error:
        st.error(f'Action refusée : {error.read().decode()}')
    except (URLError, TimeoutError):
        st.error('API indisponible. Vérifiez les services GreenMind.')
    return None



def request_control(action, **arguments):
    key = api('/identifiers/control', {})
    if key:
        return api('/simulation/controls', {
            'control_id': key['identifier'], 'action': action,
            'expected_state': state['current_state'], **arguments,
        })
    return None


st.title('🌱 GreenMind')
st.caption('Serre virtuelle · données synthétiques · aucun équipement physique')
page = st.sidebar.radio('Navigation', ['Serre', 'Console'])
st.sidebar.button('Actualiser')
state = api('/simulation')
if state:
    st.caption(f"Heure virtuelle : {state['simulated_at']} · pas {state['heure_virtuelle']}/24 · révision {state['current_state']}")
    st.info('Simulation en pause' if state['paused'] else 'Simulation en lecture')
if page == 'Console' and state:
    for column, action, label in zip(st.columns(3), ['pause', 'reprendre', 'avancer_1_heure'], ['Pause', 'Reprendre', 'Avancer d’une heure']):
        if column.button(label):
            result = request_control(action)
            if result:
                st.session_state['control'] = result['control_id']
    plant = st.selectbox('Bac à modifier', ['basilic', 'thym', 'romarin'])
    value = st.slider('Humidité imposée (%)', 0.0, 100.0, 18.0)
    if st.button('Imposer cette humidité', disabled=not state['paused']):
        result = request_control('modifier_humidite_sol', plant_id=plant, moist_request_pct=value)
        if result:
            st.session_state['control'] = result['control_id']
    if st.session_state.get('control'):
        st.write(api('/simulation/controls/' + st.session_state['control']))
else:
    plants = api('/plants') or []
    for column, plant in zip(st.columns(3), plants):
        with column:
            pid = plant['plant_id']
            st.subheader(plant['display_name'])
            st.metric('Humidité simulée', f"{plant['soil_moisture_pct']} %")
            st.write('🔴 Alerte sécheresse' if plant['has_active_alert'] else '🟢 Pas d’alerte active')
            if st.button('Proposer un arrosage', key=pid):
                proposal = api(f'/plants/{pid}/watering-proposals', {})
                if proposal:
                    st.session_state['proposal_' + pid] = proposal
                    key = api('/identifiers/command', {})
                    st.session_state['command_' + pid] = key['identifier'] if key else None
            proposal = st.session_state.get('proposal_' + pid)
            if proposal:
                st.write(proposal['reason'])
                st.caption('Expire à ' + proposal['expires_at'])
                if st.button('Confirmer cet arrosage', key='confirm_' + pid, disabled=not st.session_state.get('command_' + pid)):
                    result = api(f'/plants/{pid}/watering-commands', {'proposal_id': proposal['proposal_id'], 'command_id': st.session_state['command_' + pid]})
                    if result:
                        st.session_state['tracking_' + pid] = result['command_id']
            if st.session_state.get('tracking_' + pid):
                result = api('/watering-commands/' + st.session_state['tracking_' + pid])
                if result:
                    st.write(result['status'], result['reason'])
                    if result['measurement_pending']:
                        st.info('Mesure après arrosage en attente')
            readings = api(f'/plants/{pid}/measurements') or []
            if readings:
                st.line_chart([r['soil_moisture_pct'] for r in reversed(readings)])
    selected = st.selectbox('Journal', ['Tous les bacs'] + [p['plant_id'] for p in plants])
    suffix = '' if selected == 'Tous les bacs' else '?plant_id=' + selected
    st.dataframe(api('/events' + suffix) or [], width='stretch')
