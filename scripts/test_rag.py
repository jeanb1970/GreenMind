import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

print("Chargement de MiniLM...")
model = SentenceTransformer(MODEL, device="cpu")

documents = [
    "Le basilic nécessite un arrosage régulier.",
    "Le romarin préfère un sol relativement sec.",
    "La température influence l'évaporation de l'eau."
]

question = "Quelle plante a besoin d'eau régulièrement ?"

vectors = model.encode(documents, normalize_embeddings=True)
query = model.encode([question], normalize_embeddings=True)

vectors = np.asarray(vectors, dtype="float32")
query = np.asarray(query, dtype="float32")

index = faiss.IndexFlatIP(vectors.shape[1])
index.add(vectors)

scores, indices = index.search(query, 3)

print(f"Nombre de dimensions des vecteurs : {vectors.shape[1]}")
print(f"Documents indexés : {index.ntotal}")
print(f"Question : {question}")

for rank, (idx, score) in enumerate(zip(indices[0], scores[0]), 1):
    print(f"{rank}. {documents[idx]} (similarité : {score:.3f})")
