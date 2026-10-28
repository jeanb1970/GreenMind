"""Point d'entrée du serveur API REST FastAPI GreenMind."""

import os
import uvicorn
from greenmind.api.app import app


def main() -> int:
    host = os.environ.get("GREENMIND_API_HOST", "127.0.0.1")
    port = int(os.environ.get("GREENMIND_API_PORT", "8000"))
    uvicorn.run(app, host=host, port=port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
