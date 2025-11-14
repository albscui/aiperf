from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any, List

from pydantic import BaseModel, Field
from uuid import uuid4


class BenchmarkConfig(BaseModel):
    """Configuration for a benchmark run"""
    model: str = Field(..., description="Model to benchmark")
    url: str = Field(..., description="URL to benchmark")
    endpoint_type: str = Field(default="chat", description="Type of endpoint to benchmark")
    endpoint: str = Field(default="v1/chat/completions", description="Endpoint to benchmark")
    tokenizer: str = Field(default="gpt-4o", description="Tokenizer to use for the benchmark")

    request_count: int = Field(default=5, description="Number of requests to send")


class BenchmarkRunCreate(BaseModel):
    """Request to create a new benchmark run"""
    queue_name: str = Field(..., description="Queue this run belongs to")
    config: BenchmarkConfig


class BenchmarkRun(BaseModel):
    """A single benchmark run"""
    run_id: str = Field(default_factory=lambda: str(uuid4()))
    queue_name: str = Field(..., description="Queue this run belongs to")
    config: BenchmarkConfig


class ZMQPortAllocation(BaseModel):
    """Allocated ZMQ ports for a benchmark run"""
    event_bus_frontend: int = Field(..., description="Event bus frontend port")
    event_bus_backend: int = Field(..., description="Event bus backend port")
    dataset_frontend: int = Field(..., description="Dataset manager frontend port")
    dataset_backend: int = Field(..., description="Dataset manager backend port")
    raw_inference_frontend: int = Field(..., description="Raw inference frontend port")
    raw_inference_backend: int = Field(..., description="Raw inference backend port")
    records_port: int = Field(..., description="Records push/pull port")
    credit_drop_port: int = Field(..., description="Credit drop port")
    credit_return_port: int = Field(..., description="Credit return port")
