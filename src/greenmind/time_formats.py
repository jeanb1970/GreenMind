"""Formats belges publics ; les calculs internes utilisent des instants UTC."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import re
from typing import Annotated
from pydantic import AwareDatetime, BeforeValidator, PlainSerializer

BELGIUM = ZoneInfo('Europe/Brussels')


def local_text(value, precise=True):
    local = value.astimezone(BELGIUM)
    base = local.strftime('%Y-%m-%d %H:%M:%S')
    return base + f'.{local.microsecond:06d}'[:6] if precise else base


def parse_local(value, precise=True):
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError('Un instant Python doit préciser son fuseau horaire.')
        return value.astimezone(timezone.utc).replace(microsecond=(value.microsecond // 10 * 10) if precise else 0)
    pattern = r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}' + (r'\.\d{5}' if precise else '')
    if not isinstance(value, str) or not re.fullmatch(pattern, value):
        raise ValueError('Date belge invalide : AAAA-MM-JJ HH:MM:SS' + ('.12345' if precise else ''))
    naive = datetime.strptime(value, '%Y-%m-%d %H:%M:%S.%f' if precise else '%Y-%m-%d %H:%M:%S')
    local = naive.replace(tzinfo=BELGIUM)
    # Sans décalage dans le format demandé, une heure répétée est ambiguë.
    if local.utcoffset() != local.replace(fold=1).utcoffset():
        raise ValueError('Heure belge ambiguë ou inexistante au changement d’heure.')
    return local.astimezone(timezone.utc)


BelgianTime = Annotated[AwareDatetime, BeforeValidator(lambda v: parse_local(v, False)),
    PlainSerializer(lambda v: local_text(v, False), return_type=str, when_used='json')]
BelgianInstant = Annotated[AwareDatetime, BeforeValidator(parse_local),
    PlainSerializer(local_text, return_type=str, when_used='json')]
