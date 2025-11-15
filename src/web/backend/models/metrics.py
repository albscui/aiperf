"""
Models for metrics data
"""

from typing import Any, Dict, List

from pydantic import BaseModel, Field


class MetricPoint(BaseModel):
    """A single metric data point"""
    
    topic: str = Field(..., description="Metric topic (e.g., realtime_metrics, realtime_telemetry_metrics)")
    timestamp: str = Field(..., description="ISO timestamp when metric was received")
    data: Dict[str, Any] = Field(..., description="Metric data payload")


class MetricsResponse(BaseModel):
    """Response for profile metrics"""
    
    run_id: str = Field(..., description="Profile run ID")
    metrics: List[MetricPoint] = Field(..., description="List of metric data points")
    total_count: int = Field(..., description="Total number of metrics")
    
    # Optional: Summary statistics
    topics: List[str] = Field(default_factory=list, description="List of unique topics present")

