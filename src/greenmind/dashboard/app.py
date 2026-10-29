"""Point d'entrée Streamlit : navigation, apparence et fragments périodiques."""
from pathlib import Path
import streamlit as st
from greenmind.dashboard.client import api
from greenmind.dashboard.style import apply_style, hero
from greenmind.dashboard.views import (
    render_status, render_console, render_greenhouse, render_assistant,
)
from greenmind.simulation_rules import is_connected

LOGO = Path(__file__).with_name('assets') / 'greenmind-logo.png'
st.set_page_config(page_icon=LOGO, layout='wide')
st.logo(LOGO, size='large')

with st.sidebar:
    page = st.radio('Navigation', ['Serre', 'Console'])
    st.caption('Suivi des bacs' if page == 'Serre' else 'Mode simulation')
    appearance = st.segmented_control('Apparence', ['Clair', 'Sombre'], default='Clair',
                                     selection_mode='single', required=True, key='appearance')
    st.button('Actualiser', width='stretch', key='refresh')
apply_style(appearance)
title = 'Serre' if page == 'Serre' else 'Console · Mode simulation'
st.set_page_config(page_title='GreenMind · ' + title)
hero(title, console=page == 'Console')


@st.fragment(run_every=5)
def render_live():
    state = api('/simulation')
    connected = is_connected(state)
    render_status(state, connected)
    if page == 'Console':
        render_console(state, connected)
    else:
        render_greenhouse(state, connected)


render_live()
if page == 'Serre':
    render_assistant()
