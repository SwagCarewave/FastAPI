from fastapi import APIRouter
from app.ruview.state import state

router = APIRouter(prefix="/api")


@router.get("/status")
async def get_status():
    return {"hardware_connected": state.hardware_connected}


@router.get("/presence")
async def get_presence():
    return {
        "status": "재실" if state.stable_presence else "공실",
        "detected_at": state.detected_at,
    }
