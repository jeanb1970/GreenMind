"""Formats français pour les valeurs affichées, sans arrondir les données."""
import re


def percent(value: float | None) -> str:
    return '—' if value is None else f'{value:.2f}'.replace('.', ',') + ' %'


def percentage_text(text: str) -> str:
    """Formate aussi les anciens libellés sans réécrire le journal persistant."""
    return re.sub(r'\d+(?:[.,]\d+)?\s*%',
                  lambda match: percent(float(match.group().rstrip('%').strip().replace(',', '.'))),
                  text)
