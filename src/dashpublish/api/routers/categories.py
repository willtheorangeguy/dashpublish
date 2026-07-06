"""Category CRUD."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from dashpublish.api.deps import get_db_path
from dashpublish.db import repo
from dashpublish.db.engine import session_scope
from dashpublish.db.schemas import CategoryIn, CategoryOut

router = APIRouter(prefix="/categories", tags=["categories"])

_PATCHABLE = {"name", "query_text", "threshold", "save_top", "rerank", "enabled"}


class CategoryPatch(BaseModel):
    name: str | None = None
    query_text: str | None = None
    threshold: float | None = None
    save_top: int | None = None
    rerank: bool | None = None
    enabled: bool | None = None


@router.get("", response_model=list[CategoryOut])
def list_categories(db_path: str = Depends(get_db_path)) -> list[CategoryOut]:
    with session_scope(db_path) as session:
        return [CategoryOut.model_validate(c) for c in repo.list_categories(session)]


@router.post("", response_model=CategoryOut, status_code=201)
def create_category(data: CategoryIn, db_path: str = Depends(get_db_path)) -> CategoryOut:
    with session_scope(db_path) as session:
        if repo.get_category_by_name(session, data.name) is not None:
            raise HTTPException(status_code=409, detail=f"Category {data.name!r} already exists")
        return CategoryOut.model_validate(repo.create_category(session, data))


@router.patch("/{category_id}", response_model=CategoryOut)
def patch_category(
    category_id: int, patch: CategoryPatch, db_path: str = Depends(get_db_path)
) -> CategoryOut:
    fields: dict[str, Any] = {
        k: v for k, v in patch.model_dump(exclude_unset=True).items() if k in _PATCHABLE
    }
    with session_scope(db_path) as session:
        category = repo.update_category(session, category_id, **fields)
        if category is None:
            raise HTTPException(status_code=404, detail=f"Category {category_id} not found")
        return CategoryOut.model_validate(category)


@router.delete("/{category_id}", status_code=204)
def delete_category(category_id: int, db_path: str = Depends(get_db_path)) -> None:
    with session_scope(db_path) as session:
        category = repo.get_category(session, category_id)
        if category is None:
            raise HTTPException(status_code=404, detail=f"Category {category_id} not found")
        if category.is_builtin:
            raise HTTPException(status_code=409, detail="Cannot delete a built-in category")
        repo.delete_category(session, category_id)
