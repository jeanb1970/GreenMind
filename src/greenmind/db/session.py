"""Création et configuration des connexions SQLite de GreenMind."""

from pathlib import Path

from sqlalchemy import URL, Engine, MetaData, create_engine, event, inspect
from sqlalchemy.exc import SQLAlchemyError

from greenmind.db.models import Base


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATABASE_PATH = PROJECT_ROOT / "outputs/greenmind.sqlite"
BUSY_TIMEOUT_MS = 5000


def create_database_engine(
    database_path: Path = DEFAULT_DATABASE_PATH,
    *, metadata: MetaData = Base.metadata,
) -> Engine:
    """Prépare la base et retourne un moteur réutilisable par le processus."""
    database_path = database_path.resolve()

    try:
        database_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise RuntimeError(
            f"Impossible de préparer le dossier de la base : "
            f"{database_path.parent}."
        ) from error

    engine = create_engine(
        URL.create("sqlite+pysqlite", database=str(database_path)),
        connect_args={
            "timeout": BUSY_TIMEOUT_MS / 1000,
            "check_same_thread": False,
        },
    )

    @event.listens_for(engine, "connect")
    def configure_connection(dbapi_connection, connection_record):
        """Applique les paramètres à chaque nouvelle connexion physique."""
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
            cursor.execute("PRAGMA foreign_keys = ON")
        finally:
            cursor.close()

    try:
        with engine.connect() as connection:
            journal_mode = connection.exec_driver_sql(
                "PRAGMA journal_mode = WAL"
            ).scalar_one()

            if journal_mode.lower() != "wal":
                raise RuntimeError(
                    "SQLite n'a pas activé le mode de journalisation WAL."
                )

        # Crée les tables absentes sans supprimer les données existantes.
        # create_all ne migre pas : refuser un schéma existant incompatible.
        inspector = inspect(engine)
        if inspector.has_table("sensor_readings"):
            existing = {c["name"] for c in inspector.get_columns("sensor_readings")}
            expected = set(metadata.tables["sensor_readings"].columns.keys())
            # Migration additive : les anciennes mesures appartiennent au cycle 1.
            if expected - existing == {"cycle"} and not existing - expected:
                with engine.begin() as connection:
                    connection.exec_driver_sql("ALTER TABLE sensor_readings ADD COLUMN cycle INTEGER NOT NULL DEFAULT 1")
                existing.add("cycle")
            if existing != expected:
                raise RuntimeError("Schéma SQLite incompatible ; arrêter les services puis lancer PYTHONPATH=src .venv/bin/python scripts/reset_database.py pour reconstruire la base (historique effacé).")
        metadata.create_all(engine)

    except SQLAlchemyError as error:
        engine.dispose()
        raise RuntimeError(
            f"Impossible d'initialiser la base SQLite : {database_path}."
        ) from error
    except RuntimeError:
        engine.dispose()
        raise

    return engine
