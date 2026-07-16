from fastapi import APIRouter, HTTPException

from app.services.fact_timeline import (
    backfill_fact_event_dates,
    get_dimension_list,
    get_dimension_timeline,
    get_timeline_summary,
)

router = APIRouter(
    prefix="/api/v1/timeline",
    tags=["Timeline"],
)


def _handle_timeline_error(error):
    detail = str(error)
    if detail in {
        "invalid_dimension",
        "invalid_grain",
        "invalid_date_range",
        "date_parse_failed",
    }:
        raise HTTPException(status_code=400, detail=detail) from error
    raise HTTPException(status_code=500, detail=f"Timeline API failed: {error}") from error


@router.get("/dimensions")
def read_timeline_dimensions(dimension: str = None, limit: int = 100):
    try:
        return get_dimension_list(dimension=dimension, limit=limit)
    except ValueError as error:
        _handle_timeline_error(error)


@router.get("/technology/{technology}")
def read_technology_timeline(
    technology: str,
    grain: str = "year",
    date_from: str = None,
    date_to: str = None,
    limit: int = 100,
    include_unknown_dates: bool = False,
    include_coarse_dates: bool = False,
):
    try:
        return get_dimension_timeline(
            "technology",
            technology,
            grain=grain,
            date_from=date_from,
            date_to=date_to,
            limit=limit,
            include_unknown_dates=include_unknown_dates,
            include_coarse_dates=include_coarse_dates,
        )
    except ValueError as error:
        _handle_timeline_error(error)


@router.get("/country/{country}")
def read_country_timeline(
    country: str,
    grain: str = "year",
    date_from: str = None,
    date_to: str = None,
    limit: int = 100,
    include_unknown_dates: bool = False,
    include_coarse_dates: bool = False,
):
    try:
        return get_dimension_timeline(
            "country",
            country,
            grain=grain,
            date_from=date_from,
            date_to=date_to,
            limit=limit,
            include_unknown_dates=include_unknown_dates,
            include_coarse_dates=include_coarse_dates,
        )
    except ValueError as error:
        _handle_timeline_error(error)


@router.get("/organization/{organization}")
def read_organization_timeline(
    organization: str,
    grain: str = "year",
    date_from: str = None,
    date_to: str = None,
    limit: int = 100,
    include_unknown_dates: bool = False,
    include_coarse_dates: bool = False,
):
    try:
        return get_dimension_timeline(
            "organization",
            organization,
            grain=grain,
            date_from=date_from,
            date_to=date_to,
            limit=limit,
            include_unknown_dates=include_unknown_dates,
            include_coarse_dates=include_coarse_dates,
        )
    except ValueError as error:
        _handle_timeline_error(error)


@router.get("/summary")
def read_timeline_summary(
    date_from: str = None,
    date_to: str = None,
    grain: str = "year",
):
    try:
        return get_timeline_summary(
            date_from=date_from,
            date_to=date_to,
            grain=grain,
        )
    except ValueError as error:
        _handle_timeline_error(error)


@router.post("/backfill-dates")
def backfill_timeline_dates(dry_run: bool = True, force: bool = False):
    try:
        return backfill_fact_event_dates(dry_run=dry_run, force=force)
    except ValueError as error:
        _handle_timeline_error(error)
