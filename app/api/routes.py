from fastapi import APIRouter
from app.ruview.state import state

router = APIRouter(prefix="/api")


@router.get("/breathing")
async def get_breathing():
    if state.latest_data is None:
        return {"breathing_rate": None, "heart_rate": None, "timestamp": None}

    dominant_freq = state.latest_data.get("dominant_freq_hz", 0)
    breathing_rate = round(dominant_freq * 60)

    return {
        "breathing_rate": breathing_rate,
        "heart_rate": state.heart_rate,
        "timestamp": state.latest_data.get("timestamp"),
    }


@router.get("/presence")
async def get_presence():
    if state.latest_data is None:
        return {"is_present": False, "status": "공실", "detected_at": None}

    is_present = state.latest_data.get("presence", False)
    detected_at = state.presence_changed_at.isoformat() if state.presence_changed_at else None

    return {
        "is_present": is_present,
        "status": "재실" if is_present else "공실",
        "detected_at": detected_at,
    }
