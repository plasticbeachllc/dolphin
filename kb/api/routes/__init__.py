"""Route modules for the Knowledge Store API."""

from .files import router as files_router
from .health import router as health_router
from .repos import router as repos_router
from .search import router as search_router
from .tasks import router as tasks_router

__all__ = [
    "files_router",
    "health_router",
    "repos_router",
    "search_router",
    "tasks_router",
]
