"""Index FAISS local : empreintes, citations exactes et publication atomique."""
from dataclasses import asdict
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import tempfile
from uuid import uuid4
from greenmind.rag.corpus import CORPUS, PLANTS, ROOT, load_corpus

MODEL_NAME = 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'
MODEL_REVISION = 'e8f8c211226b894fcb81acc59f3b34ba3efd5f42'
INDEX_ROOT = ROOT / 'outputs/rag/knowledge'


def local_encoder():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(MODEL_NAME, revision=MODEL_REVISION,
                               local_files_only=True, device='cpu')


def vectorize(encoder, texts):
    import numpy as np
    vectors = np.asarray(encoder.encode(texts, normalize_embeddings=True), dtype='float32')
    if vectors.ndim != 2 or vectors.shape[0] != len(texts) or vectors.shape[1] == 0:
        raise ValueError('Dimensions des embeddings incohérentes.')
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    if not np.isfinite(vectors).all() or (norms <= 0).any():
        raise ValueError('Embeddings non finis ou nuls.')
    return np.ascontiguousarray(vectors / norms)


def build_index(encoder, directory=CORPUS, output=INDEX_ROOT):
    import faiss
    passages = load_corpus(directory)
    texts = [f'{p.title} — {p.section}\n{p.excerpt}' for p in passages]
    vectors = vectorize(encoder, texts)
    index = faiss.IndexFlatIP(vectors.shape[1])
    index.add(vectors)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    generation = 'generation_' + uuid4().hex
    target = output / generation
    target.mkdir()
    index_path = target / 'index.faiss'
    faiss.write_index(index, str(index_path))
    manifest = dict(manifest_version=1, model_name=MODEL_NAME, model_revision=MODEL_REVISION,
                    dimensions=index.d, vector_count=index.ntotal,
                    index_sha256=sha256(index_path.read_bytes()).hexdigest(),
                    passages=[asdict(p) for p in passages])
    (target / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    # Le lecteur ne voit que des générations complètes ; l'ancienne reste lisible
    # si un nouveau build échoue avant le remplacement atomique du pointeur.
    with tempfile.NamedTemporaryFile(mode='w', dir=output, delete=False, encoding='utf-8') as handle:
        handle.write(generation)
        pointer = Path(handle.name)
    os.replace(pointer, output / 'CURRENT')
    return manifest


class KnowledgeIndex:
    def __init__(self, index, passages, encoder):
        self.index, self.passages, self.encoder = index, passages, encoder

    def search(self, question, plant_id, limit=3):
        if plant_id not in PLANTS:
            raise ValueError('Plante inconnue.')
        if not isinstance(question, str) or not question.strip() or len(question) > 1000:
            raise ValueError('La question doit contenir entre 1 et 1000 caractères.')
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 5:
            raise ValueError('La limite doit être un entier entre 1 et 5.')
        query = vectorize(self.encoder, [question])
        if query.shape[1] != self.index.d:
            raise ValueError('Le modèle de requête ne correspond pas à l’index.')
        scores, positions = self.index.search(query, self.index.ntotal)
        matches = []
        for score, position in zip(scores[0], positions[0]):
            if position < 0:
                continue
            passage = self.passages[int(position)]
            if passage.plant_id == plant_id:
                matches.append({**passage.citation(), 'score': float(score)})
            if len(matches) == limit:
                break
        return matches


def load_index(encoder, directory=CORPUS, output=INDEX_ROOT):
    import faiss
    output = Path(output)
    try:
        generation = (output / 'CURRENT').read_text().strip()
        if not re.fullmatch(r'generation_[0-9a-f]{32}', generation):
            raise ValueError('Pointeur d’index invalide.')
        target = output / generation
        manifest = json.loads((target / 'manifest.json').read_text())
        if (manifest['manifest_version'] != 1 or manifest['model_name'] != MODEL_NAME
                or manifest['model_revision'] != MODEL_REVISION):
            raise ValueError('Version ou modèle de l’index incompatible ; reconstruire l’index.')
        passages = load_corpus(directory)
        if manifest['passages'] != [asdict(p) for p in passages]:
            raise ValueError('Corpus modifié ; reconstruire l’index.')
        index_path = target / 'index.faiss'
        if sha256(index_path.read_bytes()).hexdigest() != manifest['index_sha256']:
            raise ValueError('Empreinte FAISS incohérente ; reconstruire l’index.')
        index = faiss.read_index(str(index_path))
        if index.ntotal != len(passages) or index.ntotal != manifest['vector_count'] or index.d != manifest['dimensions']:
            raise ValueError('Dimensions ou passages incohérents ; reconstruire l’index.')
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise ValueError('Index absent ou manifeste invalide ; reconstruire l’index.') from error
    return KnowledgeIndex(index, passages, encoder)
