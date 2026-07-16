from fastapi import APIRouter, HTTPException

from app.services.change_dashboard import get_daily_dashboard

router = APIRouter(
    prefix="/api/v1/dashboard",
    tags=["Dashboard"],
)


@router.get("/daily")
def get_daily_change_dashboard():
    try:
        return get_daily_dashboard()
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load daily dashboard: {error}",
        ) from error
