from src.routers.ingest import router as ingest_router
from src.routers.nodes import router as nodes_router
from src.routers.stats import router as stats_router
from src.routers.events import router as events_router
from src.routers.health import router as health_router

__all__ = [
    "ingest_router",
    "nodes_router",
    "stats_router",
    "events_router",
    "health_router",
]
