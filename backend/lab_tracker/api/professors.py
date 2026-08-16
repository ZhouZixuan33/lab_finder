"""Professor list, detail, and tag endpoints."""

from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from lab_tracker.api.dependencies import get_database_path
from lab_tracker.models.common import ApplicationState
from lab_tracker.models.professor import ProfessorDetail, ProfessorListItem, TagCount
from lab_tracker.services.catalog import CatalogService

router = APIRouter(prefix="/api", tags=["professors"])


class PaginationMetadata(BaseModel):
    page: int
    page_size: int
    total: int
    pages: int


class ProfessorListResponse(BaseModel):
    items: list[ProfessorListItem]
    pagination: PaginationMetadata


class TagListResponse(BaseModel):
    items: list[TagCount]


@router.get("/professors", response_model=ProfessorListResponse)
def list_professors(
    database_path: Annotated[Path, Depends(get_database_path)],
    q: str | None = None,
    tags: str | None = None,
    state: ApplicationState | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
    sort: Literal["name", "title", "updated_at", "state"] = "name",
    order: Literal["asc", "desc"] = "asc",
) -> ProfessorListResponse:
    parsed_tags = [tag.strip() for tag in tags.split(",") if tag.strip()] if tags else []
    items, total = CatalogService(database_path).list_professors(
        search=q,
        tags=parsed_tags,
        state=state,
        page=page,
        page_size=page_size,
        sort=sort,
        order=order,
    )
    return ProfessorListResponse(
        items=items,
        pagination=PaginationMetadata(
            page=page,
            page_size=page_size,
            total=total,
            pages=(total + page_size - 1) // page_size,
        ),
    )


@router.get("/professors/{professor_id}", response_model=ProfessorDetail)
def get_professor(
    professor_id: int,
    database_path: Annotated[Path, Depends(get_database_path)],
) -> ProfessorDetail:
    return CatalogService(database_path).get_professor(professor_id)


@router.get("/tags", response_model=TagListResponse)
def list_tags(
    database_path: Annotated[Path, Depends(get_database_path)],
) -> TagListResponse:
    return TagListResponse(items=CatalogService(database_path).list_tags())
