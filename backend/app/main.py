"""Coordinator API. Run exactly one process; workers own live simulations."""
import asyncio
from contextlib import asynccontextmanager
import os
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException
from app.api.rooms import router
from app.api.ws import router as ws_router
from app.services.workers import WorkerHub
from app.db.connection import make_engine, sessions
from app.protocol import Health
from app.services.rooms import RoomError, Rooms


@asynccontextmanager
async def lifespan(app):
    """Own the coordinator pool and cleanup task from startup through shutdown."""
    engine = make_engine()
    rooms = Rooms(sessions(engine))
    try:
        # psycopg is synchronous. Move SQL work off the async event loop so it
        # cannot block future WebSocket connections or other async handlers.
        await asyncio.to_thread(rooms.start)
        app.state.rooms = rooms
        app.state.game_hub = WorkerHub(rooms)
        async def cleanup():
            """Expire rooms even when nobody calls the API or health endpoint."""
            while True:
                await asyncio.sleep(30)
                try:
                    await asyncio.to_thread(rooms.count)
                except SQLAlchemyError:
                    # Health returns 503 while SQL is unavailable; retry cleanup next interval.
                    pass
        task = asyncio.create_task(cleanup())
        try:
            yield
        finally:
            await app.state.game_hub.close()
            # Stop cleanup before disposing the database pool.
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
    finally:
        engine.dispose()


app = FastAPI(title="dodgewuh coordinator", version="0.1.0", lifespan=lifespan)
# Hackathon setting: any origin may call the REST API (tunnels change URL every restart).
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_methods=['*'], allow_headers=['*'])
app.include_router(router)
app.include_router(ws_router)


def error(status, code, message):
    """Use plan 03's JSON error envelope for every handled HTTP failure."""
    return JSONResponse(status_code=status, content={"code": code, "message": message}, headers={"Cache-Control": "no-store"})


@app.exception_handler(RoomError)
async def room_error(request, exc):
    return error(exc.status, exc.code, exc.message)


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    # Do not echo validation input: request data may eventually contain credentials.
    return error(422, "BAD_MESSAGE", "Malformed request")


@app.exception_handler(HTTPException)
async def http_error(request, exc):
    return error(exc.status_code, "BAD_MESSAGE", "Request rejected")


@app.exception_handler(SQLAlchemyError)
async def database_error(request, exc):
    # Keep database internals and connection details out of public responses.
    return error(503, "SERVER_BUSY", "Database unavailable")


@app.exception_handler(Exception)
async def unexpected_error(request, exc):
    return error(500, "SERVER_BUSY", "Internal server error")


@app.get("/api/health", response_model=Health)
def health(request: Request):
    """Report SQL readiness and active room count; SQL failures become HTTP 503."""
    return Health(build=os.getenv("BUILD_SHA", "dev"), rooms=request.app.state.rooms.count())
