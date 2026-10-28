"""Lecture stricte des trois fiches et citations par section exacte."""
from dataclasses import asdict, dataclass
from datetime import date
from hashlib import sha256
from pathlib import Path
import re
from typing import Literal
from urllib.parse import urlparse
import yaml
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

ROOT = Path(__file__).resolve().parents[3]
CORPUS = ROOT / 'knowledge'
PLANTS = ('basilic', 'thym', 'romarin')
SECTIONS = {'Besoins en eau': ('eau', 'besoins-en-eau'),
            'Substrat et drainage': ('drainage', 'substrat-et-drainage'),
            'Chaleur et culture en bac': ('chaleur_bac', 'chaleur-et-culture-en-bac')}


class Metadata(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True)
    doc_id: str
    plant_id: Literal['basilic', 'thym', 'romarin']
    title: str
    botanical_name: str
    source_title: str
    source_url: str
    consulted_on: str
    usage_note: str

    @field_validator('*')
    @classmethod
    def nonempty(cls, value):
        if not value.strip():
            raise ValueError('Métadonnée vide.')
        return value

    @field_validator('consulted_on')
    @classmethod
    def valid_date(cls, value):
        date.fromisoformat(value)
        return value

    @field_validator('source_url')
    @classmethod
    def valid_url(cls, value):
        parsed = urlparse(value)
        if parsed.scheme != 'https' or not parsed.netloc or parsed.username:
            raise ValueError('Une URL source HTTPS est obligatoire.')
        return value


@dataclass(frozen=True)
class Passage:
    doc_id: str
    chunk_id: str
    title: str
    plant_id: str
    topic: str
    section: str
    anchor: str
    source_title: str
    source_url: str
    consulted_on: str
    usage_note: str
    local_path: str
    document_sha256: str
    excerpt: str

    def citation(self):
        return {**asdict(self), 'local_link': self.local_path + '#' + self.anchor}


def load_corpus(directory=CORPUS):
    directory = Path(directory)
    paths = sorted(directory.glob('*.md'))
    if {p.name for p in paths} != {p+'.md' for p in PLANTS}:
        raise ValueError('Le corpus doit contenir exactement basilic.md, thym.md et romarin.md.')
    passages = []
    for path in paths:
        raw = path.read_bytes()
        text = raw.decode('utf-8')
        if not text.startswith('---\n') or '\n---\n' not in text[4:]:
            raise ValueError(f'{path.name} : métadonnées YAML absentes.')
        header, body = text[4:].split('\n---\n', 1)
        try:
            meta = Metadata.model_validate(yaml.safe_load(header))
        except (yaml.YAMLError, ValidationError) as error:
            raise ValueError(f'{path.name} : métadonnées invalides : {error}') from error
        if path.stem != meta.plant_id or meta.doc_id != 'fiche_' + meta.plant_id:
            raise ValueError(f'{path.name} : identité du document incohérente.')
        if not body.lstrip().startswith('# '+meta.title+'\n'):
            raise ValueError(f'{path.name} : titre incohérent.')
        parts = re.split(r'^## (.+)\n', body, flags=re.MULTILINE)
        headings = parts[1::2]
        if len(headings) != len(SECTIONS) or set(headings) != set(SECTIONS):
            raise ValueError(f'{path.name} : sections absentes, inconnues ou dupliquées.')
        for heading, content in zip(parts[1::2], parts[2::2]):
            excerpt = content.split('\nSource :', 1)[0].strip()
            if len(excerpt) < 30 or len(excerpt) > 2500 or '\n#' in excerpt:
                raise ValueError(f'{path.name} : section vide ou invalide : {heading}.')
            topic, anchor = SECTIONS[heading]
            passages.append(Passage(meta.doc_id, meta.doc_id+'::'+topic, meta.title,
                meta.plant_id, topic, heading, anchor, meta.source_title, meta.source_url,
                meta.consulted_on, meta.usage_note, 'knowledge/'+path.name,
                sha256(raw).hexdigest(), excerpt))
    return tuple(passages)
