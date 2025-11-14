import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from web.backend.models.benchmark import BenchmarkRunCreate, BenchmarkRun
from web.backend.services.queue_manager import QueueManager


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Global queue manager
queue_manager: QueueManager | None = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global queue_manager


    logger.info("Starting FastAPI backend")
    queue_manager = QueueManager()

    import asyncio
    queue_manager.queue_tasks["default"] = asyncio.create_task(queue_manager._process_queue(queue_manager.queues["default"]))

    yield

    logger.info("Shutting down FastAPI backend")
    if queue_manager is not None:
        await queue_manager.stop()
 

app = FastAPI(
    title="AIPerf Web API",
    description="Orchestrator for aiperf benchmark runs and metrics collection",
    version="0.1.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Routes
# ============================================================================

@app.get("/")
async def root():
    return {"message": "AIPerf Web API"}

@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.post("/aiperf/runs", response_model=BenchmarkRun)
async def create_aiperf_run(run: BenchmarkRunCreate):
    try:
        run = await queue_manager.submit_run(
            run.queue_name,
            run.config
        )
        return run
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("web.backend.main:app", host="0.0.0.0", port=8000)
