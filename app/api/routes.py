from fastapi import APIRouter
from app.ruview.state import state

router = APIRouter(prefix="/api")


@router.get("/status")
async def get_status():
    return {"hardware_connected": state.hardware_connected}


@router.get("/breathing")
async def get_breathing():
    if state.latest_data is None:
        return {"breathing_rate": None, "heart_rate": None, "timestamp": None, "hardware_connected": state.hardware_connected}

    breathing_rate = round(state.smoothed_freq * 60) if state.stable_presence else None
    hr = state.heart_rate if state.stable_presence else None

    return {
        "breathing_rate": breathing_rate,
        "heart_rate": hr,
        "timestamp": state.latest_data.get("timestamp"),
        "hardware_connected": state.hardware_connected,
    }


@router.get("/presence")
async def get_presence():
    if state.latest_data is None:
        return {"is_present": False, "status": "공실", "detected_at": None, "hardware_connected": state.hardware_connected}

    return {
        "is_present": state.stable_presence,
        "status": "재실" if state.stable_presence else "공실",
        "detected_at": state.detected_at,
        "hardware_connected": state.hardware_connected,
    }
