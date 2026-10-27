"""Vérifie la structure et les paramètres de la base SQLite GreenMind."""

from sqlalchemy import func, inspect, select
from sqlalchemy.exc import SQLAlchemyError

from greenmind.db.models import GreenhouseReading
from greenmind.db.session import (
    BUSY_TIMEOUT_MS,
    DEFAULT_DATABASE_PATH,
    create_database_engine,
)


def main() -> int:
    """Initialise si nécessaire la base, puis vérifie son état."""
    engine = None

    try:
        engine = create_database_engine()

        if not DEFAULT_DATABASE_PATH.is_file():
            raise RuntimeError("Le fichier SQLite est absent.")

        inspector = inspect(engine)

        if "sensor_readings" not in inspector.get_table_names():
            raise RuntimeError("La table des mesures est absente.")

        primary_key = inspector.get_pk_constraint("sensor_readings")

        if primary_key["constrained_columns"] != ["event_id"]:
            raise RuntimeError(
                "La clé primaire de la table des mesures "
                "doit être uniquement event_id."
            )
        with engine.connect() as connection:
            journal_mode = connection.exec_driver_sql(
                "PRAGMA journal_mode"
            ).scalar_one()

            busy_timeout = connection.exec_driver_sql(
                "PRAGMA busy_timeout"
            ).scalar_one()

            foreign_keys = connection.exec_driver_sql(
                "PRAGMA foreign_keys"
            ).scalar_one()

            count = connection.execute(
                select(func.count()).select_from(GreenhouseReading)
            ).scalar_one()

        if journal_mode.lower() != "wal":
            raise RuntimeError(
                "Le mode de journalisation WAL n'est pas actif."
            )

        if busy_timeout != BUSY_TIMEOUT_MS:
            raise RuntimeError(
                f"Le délai d'attente des verrous doit être de "
                f"{BUSY_TIMEOUT_MS} ms."
            )

        if foreign_keys != 1:
            raise RuntimeError(
                "Le contrôle des clés étrangères n'est pas actif."
            )

        print(f"Base SQLite : {DEFAULT_DATABASE_PATH}")
        print("Clé primaire de la table des mesures : event_id")
        print(f"Mode de journalisation : {journal_mode}")
        print(f"Délai d'attente des verrous : {busy_timeout} ms")
        print("Contrôle des clés étrangères : actif")
        print(f"Nombre de mesures enregistrées : {count}")
        print("TEST RÉUSSI : structure et paramètres SQLite vérifiés.")
        return 0

    except RuntimeError as error:
        print(f"ÉCHEC : {error}")
        return 1
    except SQLAlchemyError:
        print("ÉCHEC : une erreur SQL empêche la vérification de la base.")
        raise
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())