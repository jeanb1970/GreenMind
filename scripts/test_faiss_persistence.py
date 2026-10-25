import json
import sys
from pathlib import Path

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
OUTPUT = Path("outputs/rag")
INDEX_PATH = OUTPUT / "test_index.faiss"
MANIFEST_PATH = OUTPUT / "test_manifest.json"

documents = [
    "Le basilic nécessite un arrosage régulier.",
    "Le romarin préfère un sol relativement sec.",
    "La température influence l'évaporation de l'eau.",
]
question = "Quelle plante a besoin d'eau régulièrement ?"


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode not in ("build", "check"):
        sys.exit(
            "Utilisation : python3 scripts/test_faiss_persistence.py build|check\n"
            "  build : construire et enregistrer l'index et le manifeste.\n"
            "  check : recharger et vérifier les fichiers enregistrés."
        )
    model = SentenceTransformer(MODEL, device="cpu")
    query = np.asarray(
        model.encode([question], normalize_embeddings=True),
        dtype="float32"
    )

    if mode == "build":
        vectors = np.asarray(
            model.encode(documents, normalize_embeddings=True),
            dtype="float32"
        )

        index = faiss.IndexFlatIP(vectors.shape[1])
        index.add(vectors)

        OUTPUT.mkdir(parents=True, exist_ok=True)
        faiss.write_index(index, str(INDEX_PATH))
        MANIFEST_PATH.write_text(
            json.dumps(
                {"model": MODEL, "documents": documents},
                ensure_ascii=False, indent=2
            ),
            encoding="utf-8"
        )
        print("Index et manifeste sauvegardés.")

    else:
        index = faiss.read_index(str(INDEX_PATH))
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        assert manifest["model"] == MODEL, (
            "Le modèle indiqué dans le manifeste ne correspond pas au modèle attendu."
        )
        assert index.ntotal == len(manifest["documents"]), (
            "Le nombre de vecteurs de l'index ne correspond pas "
            "au nombre de documents du manifeste."
        )
        assert index.d == 384, (
            "Les vecteurs de l'index doivent avoir 384 dimensions."
        )
        print("Index et manifeste rechargés depuis le disque.")

    scores, indices = index.search(query, 3)

    print("Documents :", index.ntotal)
    for position, score in zip(indices[0], scores[0]):
        print(f"{documents[position]} : {score:.3f}")

    assert indices[0][0] == 0, (
        "Le premier résultat devrait être le document sur l'arrosage du basilic."
    )
    print("TEST RÉUSSI")


if __name__ == "__main__":
    main()
