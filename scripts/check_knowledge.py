"""Construire/recharger l'index B7 et vérifier les citations avec MiniLM local."""
import argparse
import json
from greenmind.rag.corpus import PLANTS, CORPUS
from greenmind.rag.index import build_index, load_index, local_encoder


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', action='store_true', help='Reconstruire explicitement l’index.')
    args = parser.parse_args()
    encoder = local_encoder()
    if args.build:
        manifest = build_index(encoder)
        print(f"Index construit : {manifest['vector_count']} passages, {manifest['dimensions']} dimensions.")
    index = load_index(encoder)
    for plant in PLANTS:
        matches = index.search(f'Comment gérer l’eau, le drainage et le dessèchement du {plant} en pot ?', plant)
        if not matches:
            raise RuntimeError(f'Aucun passage pour {plant}.')
        for match in matches:
            text = (CORPUS / (plant + '.md')).read_text()
            if match['excerpt'] not in text or match['plant_id'] != plant:
                raise RuntimeError('Citation non retrouvée dans sa fiche.')
        first = matches[0]
        print(json.dumps({key: first[key] for key in ['plant_id', 'section', 'excerpt', 'source_url', 'local_link']}, ensure_ascii=False))
    print('TEST RÉUSSI : trois fiches, index rechargé et citations vérifiées hors ligne.')


if __name__ == '__main__':
    main()
