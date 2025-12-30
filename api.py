"""FastAPI server for Reflex Docs MCP - deployable to Render."""

import os
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.reflex_docs_mcp import database
from src.reflex_docs_mcp.models import DocResult, DocPage, ComponentInfo


# Response models for the API
class SearchResponse(BaseModel):
    query: str
    results: list[dict]
    count: int


class StatsResponse(BaseModel):
    pages: int
    sections: int
    components: int


class HealthResponse(BaseModel):
    status: str
    database_ready: bool
    stats: Optional[dict] = None


# Lifespan to initialize database on startup
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database on startup."""
    print("🔧 Initializing database...")
    database.init_db()
    stats = database.get_stats()
    print(f"✅ Database ready: {stats['pages']} pages, {stats['sections']} sections, {stats['components']} components")
    yield
    print("👋 Shutting down...")


# Create FastAPI app
app = FastAPI(
    title="Reflex Docs MCP Server",
    description="API server providing structured access to Reflex documentation",
    version="0.1.0",
    lifespan=lifespan
)

# Add CORS middleware for browser access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    try:
        stats = database.get_stats()
        db_ready = stats.get("sections", 0) > 0
        return HealthResponse(
            status="healthy" if db_ready else "no_data",
            database_ready=db_ready,
            stats=stats
        )
    except Exception as e:
        return HealthResponse(
            status="error",
            database_ready=False,
            stats=None
        )


@app.get("/search", response_model=SearchResponse)
async def search_docs(
    query: str = Query(..., description="Search query"),
    limit: int = Query(10, ge=1, le=50, description="Max results")
):
    """
    Search Reflex documentation.
    
    Returns matching sections ranked by relevance.
    """
    try:
        results = database.search_sections(query, limit=limit)
        return SearchResponse(
            query=query,
            results=[r.model_dump() for r in results],
            count=len(results)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/doc/{slug:path}")
async def get_doc(slug: str):
    """
    Get a full documentation page by slug.
    
    Example: /doc/library/layout/box
    """
    page = database.get_page_sections(slug)
    if not page:
        raise HTTPException(status_code=404, detail=f"Document not found: {slug}")
    return page.model_dump()


@app.get("/components")
async def list_components(
    category: Optional[str] = Query(None, description="Filter by category")
):
    """
    List all documented Reflex components.
    
    Optionally filter by category (e.g., 'layout', 'forms').
    """
    components = database.list_all_components(category=category)
    return {
        "category": category,
        "components": [c.model_dump() for c in components],
        "count": len(components)
    }


@app.get("/component/{name}")
async def get_component(name: str):
    """
    Get details about a specific component.
    
    Example: /component/rx.button or /component/button
    """
    component = database.get_component_by_name(name)
    if not component:
        raise HTTPException(status_code=404, detail=f"Component not found: {name}")
    return component.model_dump()


@app.get("/stats", response_model=StatsResponse)
async def get_stats():
    """Get database statistics."""
    stats = database.get_stats()
    return StatsResponse(
        pages=stats["pages"],
        sections=stats["sections"],
        components=stats["components"]
    )


# For running with: python api.py
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("api:app", host="0.0.0.0", port=port, reload=True)
