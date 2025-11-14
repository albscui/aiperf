"""
AIPerf FastAPI Backend

Provides REST API for launching and managing AIPerf profile runs
with real-time metrics collection via ZMQ.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Path, Query
from fastapi.middleware.cors import CORSMiddleware

from web.backend.models import (
    MetricsResponse,
    ProfileCreateRequest,
    ProfileListResponse,
    ProfileResponse,
)
from web.backend.services.profile_controller import ProfileController
from web.backend.storage import InMemoryDatabase, ProfileRecord

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Global instances
database: InMemoryDatabase | None = None
controller: ProfileController | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    global database, controller

    logger.info("Starting AIPerf FastAPI backend")

    # Initialize database and controller
    database = InMemoryDatabase()
    controller = ProfileController(database)

    # Start the controller
    await controller.start()

    logger.info("Backend initialization complete")

    yield

    # Cleanup
    logger.info("Shutting down AIPerf backend")

    if controller:
        await controller.stop()

    logger.info("Shutdown complete")


app = FastAPI(
    title="AIPerf Web API",
    description="Orchestrator for AIPerf benchmark runs with real-time metrics collection",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Health & Status Routes
# ============================================================================


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "name": "AIPerf Web API",
        "version": "0.1.0",
        "status": "running",
    }


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy"}


# ============================================================================
# Profile Management Routes
# ============================================================================


@app.post("/aiperf/profiles", response_model=ProfileResponse, status_code=201)
async def create_profile(request: ProfileCreateRequest):
    """
    Create and submit a new AIPerf profile run.

    The profile will be added to the specified queue and executed when resources
    are available. Each queue processes jobs sequentially (one at a time).

    Real-time metrics are automatically collected via ZMQ and stored in the database.
    """
    if not controller:
        raise HTTPException(status_code=503, detail="Service not initialized")

    try:
        # Submit to controller
        profile = await controller.submit_profile(
            queue_name=request.queue_name,
            config=request.config.model_dump(),
        )

        # Convert to response model
        return _profile_to_response(profile)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error(f"Error creating profile: {e}")
        raise HTTPException(status_code=500, detail="Internal server error") from e


@app.get("/aiperf/profiles/{run_id}", response_model=ProfileResponse)
async def get_profile(
    run_id: str = Path(..., description="Unique identifier of the profile run"),
):
    """
    Get information about a specific profile run.

    Returns the current status, configuration, and timestamps for the run.
    """
    if not database:
        raise HTTPException(status_code=503, detail="Service not initialized")

    profile = await database.get_profile(run_id)

    if not profile:
        raise HTTPException(status_code=404, detail=f"Profile {run_id} not found")

    return _profile_to_response(profile)


@app.get("/aiperf/profiles", response_model=ProfileListResponse)
async def list_profiles(
    queue_name: str | None = Query(None, description="Filter by queue name"),
    status: str | None = Query(None, description="Filter by status"),
):
    """
    List all profile runs with optional filters.

    Results are sorted by creation time (most recent first).
    """
    from web.backend.storage import ProfileStatus

    if not database:
        raise HTTPException(status_code=503, detail="Service not initialized")

    # Parse status filter
    status_filter = None
    if status:
        try:
            status_filter = ProfileStatus(status)
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status: {status}. Must be one of: pending, running, completed, failed, cancelled",
            ) from e

    # Get profiles from database
    profiles = await database.list_profiles(
        queue_name=queue_name,
        status=status_filter,
    )

    # Convert to response models
    profile_responses = [_profile_to_response(p) for p in profiles]

    return ProfileListResponse(
        profiles=profile_responses,
        total=len(profile_responses),
    )


@app.get("/aiperf/profiles/{run_id}/metrics", response_model=MetricsResponse)
async def get_profile_metrics(
    run_id: str = Path(..., description="Unique identifier of the profile run"),
):
    """
    Get all metrics collected for a specific profile run.

    Metrics are collected in real-time via ZMQ as the profile executes.
    This endpoint returns all metrics received so far, even if the run is still in progress.
    """
    if not database:
        raise HTTPException(status_code=503, detail="Service not initialized")

    # Check if profile exists
    profile = await database.get_profile(run_id)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Profile {run_id} not found")

    # Get metrics
    metrics = await database.get_metrics(run_id)

    # Convert to response format
    from web.backend.models import MetricPoint

    metric_points = [
        MetricPoint(
            topic=m.topic,
            timestamp=m.timestamp.isoformat(),
            data=m.data,
        )
        for m in metrics
    ]

    # Get unique topics
    topics = list(set(m.topic for m in metrics))

    return MetricsResponse(
        run_id=run_id,
        metrics=metric_points,
        total_count=len(metric_points),
        topics=topics,
    )


# ============================================================================
# Helper Functions
# ============================================================================


def _profile_to_response(profile: ProfileRecord) -> ProfileResponse:
    """Convert ProfileRecord to ProfileResponse"""
    return ProfileResponse(
        run_id=profile.run_id,
        queue_name=profile.queue_name,
        config=profile.config,
        status=profile.status.value,
        created_at=profile.created_at.isoformat(),
        started_at=profile.started_at.isoformat() if profile.started_at else None,
        completed_at=profile.completed_at.isoformat() if profile.completed_at else None,
        error=profile.error,
    )


# ============================================================================
# Main Entry Point
# ============================================================================


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "web.backend.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
