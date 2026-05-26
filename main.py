from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import asyncio
from app.ruview.client import ruview_listener
from app.ruview.status import status_checker
from app.ruview.state import state
from app.api.routes import router

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.on_event("startup")
async def startup():
    asyncio.create_task(ruview_listener())
    asyncio.create_task(status_checker())


@app.get("/")
def root():
    return {"message": "CareWave FastAPI Server"}


@app.websocket("/ws/carewave")
async def carewave_ws(websocket: WebSocket):
    await websocket.accept()
    state.clients.append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        state.clients.remove(websocket)


@app.websocket("/ws/breathing")
async def breathing_ws(websocket: WebSocket):
    await websocket.accept()
    state.breathing_clients.append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        state.breathing_clients.remove(websocket)


@app.websocket("/ws/presence")
async def presence_ws(websocket: WebSocket):
    await websocket.accept()
    state.presence_clients.append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        state.presence_clients.remove(websocket)
