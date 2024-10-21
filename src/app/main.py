"""API entry points."""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.requests import Request
from starlette.responses import JSONResponse

from app import service, utils
from app.api import router
from app.config import settings
from app.errors import ClientError
from app.logger import L


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Execute actions on server startup and shutdown."""
    L.info(
        "Starting application [PID={}, CPU_COUNT={}]",
        os.getpid(),
        os.cpu_count(),
    )
    service.get_bundled_region_map()
    utils.warmup_executors()
    yield
    L.info("Stopping the application")


async def client_error_handler(request: Request, exc: ClientError) -> JSONResponse:
    """Handle application errors to be returned to the client."""
    # pylint: disable=unused-argument
    msg = f"{exc.__class__.__name__}: {exc}"
    L.warning(msg)
    return JSONResponse(status_code=exc.status_code, content={"message": msg})


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION or "0.0.0",
    debug=settings.APP_DEBUG,
    lifespan=lifespan,
    root_path=settings.ROOT_PATH,
    exception_handlers={
        ClientError: client_error_handler,
    },
)
app.include_router(router)
