from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import asyncio
from app.csi.udp_receiver import udp_receiver
from app.csi.state import state
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
    asyncio.create_task(udp_receiver())


@app.get("/")
def root():
    return {"message": "CareWave FastAPI Server"}


@app.websocket("/ws/presence")
async def presence_ws(websocket: WebSocket):
    await websocket.accept()
    state.presence_clients.append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except Exception:
        pass
    finally:
        if websocket in state.presence_clients:
            state.presence_clients.remove(websocket)


@app.websocket("/ws/fall")
async def fall_ws(websocket: WebSocket):
    await websocket.accept()
    state.fall_clients.append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except Exception:
        pass
    finally:
        if websocket in state.fall_clients:
            state.fall_clients.remove(websocket)
