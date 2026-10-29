"""Historique commun des trois bacs sur leur véritable horloge virtuelle."""
import altair as alt
from math import ceil
from greenmind.simulation_rules import elapsed_hours, HOURS_PER_CYCLE

from greenmind.display import percent

PLANTS = ['Basilic', 'Thym', 'Romarin']
COLORS = ['#65d934', '#166534', '#a855f7']


def moisture_chart(readings):
    rows = [
        {**r, 'heures_cumulees': elapsed_hours(r.get('cycle', 1), r['heure_virtuelle']),
         'cycle': r.get('cycle', 1), 'plante': r['plant_id'].capitalize(),
         'humidite': percent(r['soil_moisture_pct'])}
        for r in sorted(readings, key=lambda r: (
            r['current_state'], r['emitted_at'], len(r['event_id']), r['event_id']))
    ]
    last_hour = max((row['heures_cumulees'] for row in rows), default=0)
    end_hour = max(HOURS_PER_CYCLE, ceil(last_hour / HOURS_PER_CYCLE) * HOURS_PER_CYCLE)
    return alt.Chart(alt.Data(values=rows)).mark_line(point=True, strokeWidth=3).encode(
        x=alt.X('heures_cumulees:Q', title=None,
                scale=alt.Scale(domain=[0, end_hour]),
                axis=alt.Axis(tickMinStep=1, labelExpr="format(datum.value, '.0f') + ' H'")),
        y=alt.Y('soil_moisture_pct:Q', title=None,
                scale=alt.Scale(domain=[0, 100]),
                axis=alt.Axis(labelExpr="format(datum.value, '.0f') + ' %'")),
        color=alt.Color('plante:N', title='Plante',
                        scale=alt.Scale(domain=PLANTS, range=COLORS),
                        legend=alt.Legend(orient='top')),
        order=alt.Order('current_state:Q'),
        tooltip=[alt.Tooltip('plante:N', title='Plante'),
                 alt.Tooltip('cycle:Q', title='Cycle'),
                 alt.Tooltip('heure_virtuelle:Q', title='Heure du cycle'),
                 alt.Tooltip('heures_cumulees:Q', title='Heures cumulées'),
                 alt.Tooltip('humidite:N', title='Humidité du sol'),
                 alt.Tooltip('current_state:Q', title='Version de l’état'),
                 alt.Tooltip('measurement_origin:N', title='Origine')],
    ).properties(height=510).configure(font='Source Sans')
