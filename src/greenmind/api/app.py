"""Application FastAPI principale de GreenMind v1.4."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from greenmind.api.routes import router
from greenmind.api.watering import router as watering_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="GreenMind REST API",
        version="1.4.0",
        description="API REST de supervision et de contrôle de la serre GreenMind v1.4",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router)
    app.include_router(watering_router)

    return app


app = create_app()
