"""
Models for AIPerf profiles
"""

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class ProfileConfig(BaseModel):
    """Configuration for an AIPerf profile run"""

    # Required fields
    model: str = Field(..., description="Model identifier to benchmark")
    url: str = Field(..., description="Base URL of the inference server")

    # Endpoint configuration
    endpoint_type: str = Field(
        default="chat", description="Type of endpoint (chat, completions, etc)"
    )
    endpoint: str = Field(
        default="v1/chat/completions", description="Custom endpoint path"
    )
    tokenizer: str = Field(..., description="Tokenizer to use")

    # Request configuration
    request_count: int = Field(
        default=3, ge=1, description="Number of requests to send"
    )
    concurrency: int = Field(
        default=1, ge=1, description="Number of concurrent requests"
    )
    request_rate: float | None = Field(
        default=None, gt=0, description="Target request rate (req/s)"
    )


class ProfileCreateRequest(BaseModel):
    """Request to create a new profile run"""

    queue_name: str = Field(
        default="default", description="Queue to submit this profile to"
    )
    config: ProfileConfig = Field(..., description="Profile configuration")


class ProfileResponse(BaseModel):
    """Response for profile information"""

    run_id: str = Field(..., description="Unique identifier for this run")
    queue_name: str = Field(..., description="Queue this run belongs to")
    config: Dict[str, Any] = Field(..., description="Profile configuration")
    status: str = Field(
        ...,
        description="Current status (pending, running, completed, failed, cancelled)",
    )

    created_at: str = Field(..., description="ISO timestamp when run was created")
    started_at: Optional[str] = Field(
        default=None, description="ISO timestamp when run started"
    )
    completed_at: Optional[str] = Field(
        default=None, description="ISO timestamp when run completed"
    )

    error: Optional[str] = Field(
        default=None, description="Error message if run failed"
    )


class ProfileListResponse(BaseModel):
    """Response for listing profiles"""

    profiles: list[ProfileResponse] = Field(..., description="List of profiles")
    total: int = Field(..., description="Total number of profiles")
