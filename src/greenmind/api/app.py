"""Application FastAPI principale de GreenMind v1.4."""

from contextlib import asynccontextmanager
import os
from ipaddress import ip_address
import httpx2 as httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from greenmind.api.routes import router
from greenmind.api.arrosage import router as watering_router
from greenmind.api.assistant import router as assistant_router
from greenmind.rag.assistant import Assistant
from greenmind.api.dependencies import configured_simulation_mode


@asynccontextmanager
async def lifespan(app):
    async with httpx.AsyncClient(
        base_url=os.environ.get('GREENMIND_OLLAMA_URL', 'http://127.0.0.1:11434'),
        timeout=httpx.Timeout(40, connect=2), trust_env=False,
        limits=httpx.Limits(max_connections=1, max_keepalive_connections=1),
    ) as client:
        service = Assistant(client)
        app.state.assistant = service
        try:
            yield
        finally:
            await service.close()


def create_app(*, simulation_mode: bool | None = None) -> FastAPI:
    enabled = configured_simulation_mode() if simulation_mode is None else simulation_mode
    host = os.environ.get('GREENMIND_API_HOST', '127.0.0.1').strip()
    if enabled and host != 'localhost':
        try:
            loopback = ip_address(host).is_loopback
        except ValueError:
            loopback = False
        if not loopback:
            raise ValueError('Le mode simulation exige un hôte API loopback (127.0.0.1 ou ::1).')
    app = FastAPI(
        title="GreenMind REST API",
        version="1.4.0",
        description="API REST de supervision et de contrôle de la serre GreenMind v1.4",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )
    app.state.simulation_mode = enabled

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router)
    app.include_router(watering_router)
    app.include_router(assistant_router)

    return app


app = create_app()
