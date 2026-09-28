"""Normalized research-intelligence contracts and persistence."""

from typing import TYPE_CHECKING

from .models import (
    EntityDetail,
    EntityListResponse,
    EntityType,
    ResearchPaper,
    SourceEditionCreate,
)

if TYPE_CHECKING:
    from .repository import ResearchRepository

__all__ = [
    "EntityDetail",
    "EntityListResponse",
    "EntityType",
    "ResearchPaper",
    "ResearchRepository",
    "SourceEditionCreate",
]


def __getattr__(name: str):
    if name == "ResearchRepository":
        from .repository import ResearchRepository

        return ResearchRepository
    raise AttributeError(name)
