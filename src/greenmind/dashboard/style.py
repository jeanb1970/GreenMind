"""Identité visuelle locale : illustration fournie et polices incluses dans Streamlit."""
from base64 import b64encode
from functools import lru_cache
from pathlib import Path

import streamlit as st


def stylesheet(appearance='Clair'):
    assets = Path(__file__).with_name('assets')
    illustration = illustration_data()
    css = (assets / 'dashboard.css').read_text()
    if appearance == 'Clair':
        css += '\n' + (assets / 'light.css').read_text()
    return '<style>' + css.replace('__ILLUSTRATION__', illustration) + '</style>'


@lru_cache(maxsize=1)
def illustration_data():
    return b64encode((Path(__file__).with_name('assets') / 'greenmind-architecture.jpeg').read_bytes()).decode('ascii')


def apply_style(appearance='Clair'):
    st.html(stylesheet(appearance))


def hero(title, console=False):
    with st.container(key='hero'):
        st.html('<div class="hero-brand">Green<span>Mind</span><span class="hero-tag">SERRE CONNECTÉE · IA LOCALE</span></div>')
        st.title(title)
        st.caption('Pilotez le temps et les conditions de vos trois bacs.' if console
                   else 'Trois plantes, trois équilibres. Votre serre en un regard.')
        st.html('<div class="hero-note">Serre virtuelle · données synthétiques · aucun équipement physique</div>')


def plant_art(plant_id):
    # Petites illustrations vectorielles décoratives : feuilles larges, petites,
    # puis aiguilles. Aucun fichier distant ni génération au lancement.
    if plant_id == 'basilic':
        leaves = '<path d="M39 43C13 45 10 21 16 13c21-2 31 12 23 30ZM41 32C40 13 54 6 67 10c4 18-7 28-26 22Z"/><path d="M39 57C19 61 12 48 17 38c14-3 22 3 22 19ZM42 51c0-17 11-24 26-21 0 18-9 25-26 21Z"/>'
    elif plant_id == 'thym':
        leaves = ''.join(f'<ellipse cx="{x}" cy="{y}" rx="7" ry="4" transform="rotate({angle} {x} {y})"/>'
                         for x, y, angle in [(30, 20, 35), (45, 15, -40), (29, 34, 35), (48, 29, -40), (27, 47, 35), (48, 44, -40), (31, 59, 35), (48, 57, -40)])
    else:
        leaves = ''.join(f'<path d="M40 {y+10}Q{x} {y+2} {x} {y-9}Q40 {y-2} 40 {y+10}Z"/>'
                         for y in [22, 35, 48, 61] for x in [22, 58])
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 80 88"><circle cx="40" cy="40" r="37" fill="#edf7f0"/><g fill="#97d4ae" stroke="#287a58" stroke-width="1.6" stroke-linejoin="round">{leaves}</g><path d="M40 16v56M27 72h26l-4 11H31Z" fill="#d0e7da" stroke="#287a58" stroke-width="2"/></svg>'
    encoded = b64encode(svg.encode()).decode('ascii')
    st.html(f'<div class="plant-art"><img src="data:image/svg+xml;base64,{encoded}" width="70" height="77" alt="" /></div>')
