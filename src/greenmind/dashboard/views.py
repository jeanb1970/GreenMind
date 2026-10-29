"""Composants de présentation des vues Serre et Console.

Les fragments et la navigation sont assemblés par app.py ; les mutations passent
uniquement par client.py et l'API REST.
"""
import streamlit as st
from greenmind.display import percent, percentage_text
from greenmind.dashboard.charts import moisture_chart
from greenmind.dashboard.style import plant_art
from greenmind.dashboard.client import api, request_control
from greenmind.simulation_rules import elapsed_hours

def render_status(state, connected):
    if state is not None:
        with st.container(border=True, key='status'):
            if not state.get('simulation'):
                st.warning('Aucune simulation initialisée.')
            elif not state.get('simulated_at'):
                st.warning('Simulateur indisponible : aucune mesure de référence disponible.')
            else:
                st.caption(f"Cycle J{state.get('cycle', 1)} · heure du scénario : {state['simulated_at']} · pas {state['heure_virtuelle']}/24 · révision {state['current_state']}")
                st.caption(f"Temps simulé cumulé : {elapsed_hours(state.get('cycle', 1), state['heure_virtuelle'])} h · 1 h simulée = 5 s de lecture · affichage actualisé toutes les 5 s")
                if not connected:
                    st.warning('Simulateur indisponible : aucun signal de présence récent. Les valeurs affichées sont les dernières données enregistrées.')
                elif state.get('day_complete'):
                    st.info('Journée terminée · simulation en pause et connectée')
                else:
                    st.info('Simulation en pause et connectée' if state['paused'] else 'Simulation en lecture et connectée')

def render_console(state, connected):
    can_control = connected and bool(state.get('simulation_mode'))
    with st.container(border=True, key='console_panel'):
        st.subheader('Commandes de simulation')
        if state and not state.get('simulation_mode'):
            st.info('Mode simulation désactivé côté serveur : les contrôles sont indisponibles.')
        for column, action, label in zip(st.columns(3), ['pause', 'reprendre', 'avancer_1_heure'], ['Pause', 'Reprendre', 'Avancer d’une heure']):
            unavailable = not can_control or (action in ('reprendre', 'avancer_1_heure') and state.get('day_complete', False))
            if can_control:
                unavailable = unavailable or (action == 'avancer_1_heure' and not state['paused'])
            if column.button(label, disabled=unavailable):
                result = request_control(action, state)
                if result:
                    st.session_state['control'] = result['control_id']
        if st.button('Jour suivant', disabled=not can_control or not state.get('day_complete', False)):
            result = request_control('jour_suivant', state)
            if result:
                st.session_state['control'] = result['control_id']
        st.caption('Chaque cycle rejoue le même jour météo. Les bacs conservent leur état ; le cycle suivant commence en pause.')
        plant = st.selectbox('Bac à modifier', ['basilic', 'thym', 'romarin'])
        value = st.slider('Humidité imposée (%)', 0.0, 100.0, 18.0, format='%.2f', disabled=not can_control)
        if st.button('Imposer cette humidité', disabled=not can_control or not state['paused']):
            result = request_control('modifier_humidite_sol', state, plant_id=plant, moist_request_pct=value)
            if result:
                st.session_state['control'] = result['control_id']
        if st.session_state.get('control'):
            st.write(api('/simulation/controls/' + st.session_state['control']))

def render_greenhouse(state, connected):
    plants = api('/plants') or []
    with st.container(border=True, key='weather'):
        st.subheader('Météo commune')
        if state and state.get('air_temperature_c') is not None and state.get('air_humidity_pct') is not None:
            temperature, humidity = st.columns(2)
            temperature.metric('Température de l’air', f"{state['air_temperature_c']:.2f}".replace('.', ',') + ' °C')
            humidity.metric('Humidité de l’air', percent(state['air_humidity_pct']))
            st.caption('Journée synthétique illustrative — ambiance de serre' if state.get('provenance') == 'meteo_simulee'
                       else 'Météo historique du scénario — ambiance de serre')
            st.caption(f"Intervalle appliqué à partir de : {state['observed_at']}")
            if not connected:
                st.caption('Dernière météo enregistrée ; fraîcheur non confirmée.')
        else:
            st.info('Météo indisponible : aucune mesure commune enregistrée.')
    history = []
    for column, plant in zip(st.columns(3), plants):
        with column, st.container(border=True, key='bac_' + plant['plant_id']):
            pid = plant['plant_id']
            plant_art(pid)
            st.subheader(plant['display_name'])
            st.metric('Humidité du sol', percent(plant['soil_moisture_pct']))
            st.write('🔴 Alerte sécheresse' if plant['has_active_alert'] else '🟢 Pas d’alerte active')
            st.caption(f"Seuil bas : {percent(plant.get('moist_low_pct'))} · Réarmement : {percent(plant.get('moist_rearm_pct'))}")
            st.caption(f"Cible d’arrosage : {percent(plant.get('moist_target_pct'))} · Seuil haut : {percent(plant.get('moist_high_pct'))}")
            st.caption(f"Arroseur : {plant.get('arroseur_id', '—')}")
            sprinkler = plant.get('arroseur_active')
            st.caption('État à la dernière mesure : ' + ('inconnu' if sprinkler is None else 'actif' if sprinkler else 'au repos'))
            if st.button('Proposer un arrosage', key=pid, disabled=not connected):
                proposal = api(f'/plants/{pid}/arrosage-proposals', {})
                if proposal:
                    st.session_state['proposal_' + pid] = proposal
                    key = api('/identifiers/command', {})
                    st.session_state['command_' + pid] = key['identifier'] if key else None
            proposal = st.session_state.get('proposal_' + pid)
            if proposal:
                st.write(percentage_text(proposal['reason']))
                st.caption('Expire à ' + proposal['expires_at'])
                if st.button('Confirmer cet arrosage', key='confirm_' + pid, disabled=not connected or not st.session_state.get('command_' + pid)):
                    result = api(f'/plants/{pid}/arrosage-commands', {'proposal_id': proposal['proposal_id'], 'command_id': st.session_state['command_' + pid]})
                    if result:
                        st.session_state['tracking_' + pid] = result['command_id']
            if st.session_state.get('tracking_' + pid):
                result = api('/arrosage-commands/' + st.session_state['tracking_' + pid])
                if result:
                    st.write(result['status'], percentage_text(result['reason']))
                    if result['measurement_pending']:
                        st.info('Mesure après arrosage en attente')
            history.extend(api(f'/plants/{pid}/measurements?limit=1000&include_presence=false') or [])
    with st.container(border=True, key='history'):
        st.subheader('Évolution de l’humidité du sol')
        if history:
            st.altair_chart(moisture_chart(history), width='stretch')
            st.caption('Les points suivent les heures virtuelles ; les interventions à une même heure sont reliées dans l’ordre des versions d’état. Les signaux de présence sont exclus. Jusqu’à 1 000 mesures récentes par bac, avec continuité entre les cycles.')
        else:
            st.info('Aucune mesure disponible pour cette simulation.')
    with st.container(border=True, key='journal'):
        st.subheader('Journal de la serre')
        selected = st.selectbox('Journal', ['Tous les bacs'] + [p['plant_id'] for p in plants])
        suffix = '' if selected == 'Tous les bacs' else '?plant_id=' + selected
        events = api('/events' + suffix) or []
        st.dataframe([{**event, 'summary': percentage_text(event['summary'])} for event in events], width='stretch')


def render_assistant():
    with st.container(border=True, key='assistant'):
        st.subheader('Assistant horticole local')
        @st.fragment(run_every=10)
        def assistant_status():
            health = api('/assistant/health', timeout=3)
            if isinstance(health, dict) and health.get('available'):
                st.success('Assistant disponible · ' + health['reason'])
            elif isinstance(health, dict):
                st.warning('Assistant ' + health.get('status', 'indisponible') + ' · ' + health.get('reason', ''))
            else:
                st.warning('Disponibilité de l’assistant non vérifiée.')
        assistant_status()
        st.caption('Les mesures sont fournies par GreenMind ; l’explication s’appuie sur les fiches sourcées. Aucune action n’est exécutée par le chat.')
        assistant_plant = st.selectbox('Plante de la question', ['basilic', 'thym', 'romarin'], key='assistant_plant')
        with st.form('assistant_question'):
            question = st.text_input('Votre question', max_chars=1000, placeholder='Pourquoi le thym a-t-il besoin d’un sol drainant ?')
            submitted = st.form_submit_button('Poser la question')
        if submitted and question.strip():
            with st.spinner('Recherche des sources et génération locale…'):
                result = api('/assistant/ask', {'plant_id': assistant_plant, 'question': question}, timeout=45)
            if result:
                st.session_state['assistant_result'] = result
        result = st.session_state.get('assistant_result')
        if result and result['plant_id'] == assistant_plant:
            st.markdown('**Faits de la serre au moment de la question**')
            facts = result['facts']
            st.json({key: percent(value) if key.endswith('_pct') else value
                     for key, value in facts.items()}, expanded=False)
            if facts.get('measurement_origin') == 'modification_manuelle':
                st.caption('Cette humidité a été imposée manuellement dans la simulation ; elle ne provient pas d’un capteur physique.')
            if not facts.get('fresh'):
                st.warning('Ces mesures ne sont pas récentes. Actualisez la serre avant toute décision.')
            st.markdown('**Explication documentaire**')
            if result['status'] == 'répondu':
                st.write(result['explanation'])
            else:
                st.info(result['explanation'])
            for citation in result['sources']:
                with st.expander(f"{citation['citation_id']} — {citation['title']} · {citation['section']}"):
                    st.write(citation['excerpt'])
                    st.link_button('Consulter la source', citation['source_url'])
                    st.caption(f"{citation['local_link']} · consulté le {citation['consulted_on']}")
                    st.caption(citation['usage_note'])
