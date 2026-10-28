"""B7 : provenance, invalidation et correspondance exacte vecteur/citation."""
from dataclasses import asdict
import json
from pathlib import Path
import shutil
import numpy as np
import pytest
from greenmind.rag.corpus import CORPUS, load_corpus
from greenmind.rag.index import build_index, load_index


class Encoder:
    """Embeddings déterministes pour tester le stockage sans charger de modèle."""
    def encode(self, texts, **kwargs):
        return np.array([[1 + t.lower().count('eau'), 1 + t.lower().count('drain'),
                          1 + t.lower().count('pot')] for t in texts], dtype='float32')


@pytest.fixture
def corpus(tmp_path):
    path = tmp_path / 'knowledge'
    shutil.copytree(CORPUS, path)
    return path


def test_three_complete_sourced_sheets():
    passages = load_corpus()
    assert len(passages) == 9
    assert len({p.chunk_id for p in passages}) == 9
    assert {p.plant_id for p in passages} == {'basilic', 'thym', 'romarin'}
    for p in passages:
        assert p.excerpt in (CORPUS / (p.plant_id+'.md')).read_text()
        assert p.source_url.startswith('https://')
        assert p.citation()['local_link'].startswith('knowledge/')


@pytest.mark.parametrize('change', ['empty', 'no_source', 'bad_date', 'wrong_plant', 'empty_section', 'duplicate_section', 'missing_file'])
def test_invalid_sheet_is_rejected(corpus, change):
    path = corpus / 'basilic.md'
    text = path.read_text()
    if change == 'empty': text = ''
    if change == 'no_source': text = '\n'.join(l for l in text.splitlines() if not l.startswith('source_url:'))
    if change == 'bad_date': text = text.replace('2026-10-28', '28/10/2026')
    if change == 'wrong_plant': text = text.replace('plant_id: basilic', 'plant_id: thym')
    if change == 'empty_section':
        text = text.split('## Besoins en eau')[0] + '## Besoins en eau\n\n' + '## Substrat et drainage' + text.split('## Substrat et drainage')[1]
    if change == 'duplicate_section': text += '\n## Besoins en eau\n\nUn doublon de section doit être refusé.\n'
    if change == 'missing_file':
        path.unlink()
    else:
        path.write_text(text)
    with pytest.raises(ValueError):
        load_corpus(corpus)


def test_build_reload_filter_and_citations(corpus, tmp_path):
    encoder = Encoder()
    output = tmp_path / 'index'
    manifest = build_index(encoder, corpus, output)
    index = load_index(encoder, corpus, output)
    assert manifest['passages'] == [asdict(p) for p in load_corpus(corpus)]
    for plant in ['basilic', 'thym', 'romarin']:
        matches = index.search('Eau et drainage en pot', plant)
        assert len(matches) == 3
        assert all(m['plant_id'] == plant for m in matches)
        assert all(m['excerpt'] in (corpus / (plant+'.md')).read_text() for m in matches)
        assert matches[0]['score'] >= matches[-1]['score']


def test_corpus_change_requires_rebuild(corpus, tmp_path):
    output = tmp_path / 'index'
    build_index(Encoder(), corpus, output)
    path = corpus / 'basilic.md'
    path.write_text(path.read_text()+'\n')
    with pytest.raises(ValueError, match='Corpus modifié'):
        load_index(Encoder(), corpus, output)
    build_index(Encoder(), corpus, output)
    assert load_index(Encoder(), corpus, output)


def test_corrupt_index_and_manifest_are_rejected(corpus, tmp_path):
    output = tmp_path / 'index'
    build_index(Encoder(), corpus, output)
    generation = (output / 'CURRENT').read_text()
    path = output / generation / 'index.faiss'
    path.write_bytes(path.read_bytes()+b'corrupt')
    with pytest.raises(ValueError, match='Empreinte'):
        load_index(Encoder(), corpus, output)
    build_index(Encoder(), corpus, output)
    path = output / (output / 'CURRENT').read_text() / 'manifest.json'
    manifest = json.loads(path.read_text())
    manifest['model_revision'] = 'autre-modele'
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='modèle'):
        load_index(Encoder(), corpus, output)


def test_failed_build_keeps_previous_generation(corpus, tmp_path):
    output = tmp_path / 'index'
    build_index(Encoder(), corpus, output)
    previous = (output / 'CURRENT').read_text()
    class BrokenEncoder:
        def encode(self, *args, **kwargs): raise RuntimeError('Modèle indisponible')
    with pytest.raises(RuntimeError):
        build_index(BrokenEncoder(), corpus, output)
    assert (output / 'CURRENT').read_text() == previous
    assert load_index(Encoder(), corpus, output)


@pytest.mark.parametrize('question,plant,limit', [('', 'basilic', 3), ('eau', 'inconnu', 3), ('eau', 'thym', 0)])
def test_search_rejects_invalid_parameters(corpus, tmp_path, question, plant, limit):
    output = tmp_path / 'index'
    build_index(Encoder(), corpus, output)
    with pytest.raises(ValueError):
        load_index(Encoder(), corpus, output).search(question, plant, limit)
