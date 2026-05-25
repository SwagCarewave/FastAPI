from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import asyncio
from app.ruview.websocket_client import ruview_manager

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    asyncio.create_task(ruview_manager.connect_ruview())


@app.get("/")
def root():
    return {"message": "CareWave FastAPI Server"}


@app.websocket("/ws/carewave")
async def carewave_ws(websocket: WebSocket):
    await ruview_manager.connect_client(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ruview_manager.disconnect_client(websocket)