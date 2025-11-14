"""
In-memory database implementation.

This module provides a simple in-memory storage layer that can be easily
swapped out for Postgres or DuckDB later.
"""

import asyncio
from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4


class ProfileStatus(Enum):
    """Status of an AIPerf profile run"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ProfileRecord:
    """Represents an AIPerf profile run"""
    
    def __init__(
        self,
        run_id: str,
        queue_name: str,
        config: Dict[str, Any],
        status: ProfileStatus = ProfileStatus.PENDING,
        created_at: Optional[datetime] = None,
    ):
        self.run_id = run_id
        self.queue_name = queue_name
        self.config = config
        self.status = status
        self.created_at = created_at or datetime.utcnow()
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None
        self.error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "run_id": self.run_id,
            "queue_name": self.queue_name,
            "config": self.config,
            "status": self.status.value,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error": self.error,
        }


class MetricRecord:
    """Represents a metric update for a profile run"""
    
    def __init__(
        self,
        run_id: str,
        topic: str,
        data: Dict[str, Any],
        timestamp: Optional[datetime] = None,
    ):
        self.run_id = run_id
        self.topic = topic
        self.data = data
        self.timestamp = timestamp or datetime.utcnow()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "run_id": self.run_id,
            "topic": self.topic,
            "data": self.data,
            "timestamp": self.timestamp.isoformat(),
        }


class DatabaseInterface(ABC):
    """Abstract interface for database operations"""
    
    @abstractmethod
    async def create_profile(self, profile: ProfileRecord) -> ProfileRecord:
        """Create a new profile record"""
        pass
    
    @abstractmethod
    async def get_profile(self, run_id: str) -> Optional[ProfileRecord]:
        """Get a profile by ID"""
        pass
    
    @abstractmethod
    async def update_profile_status(
        self,
        run_id: str,
        status: ProfileStatus,
        error: Optional[str] = None,
    ) -> None:
        """Update profile status"""
        pass
    
    @abstractmethod
    async def list_profiles(
        self,
        queue_name: Optional[str] = None,
        status: Optional[ProfileStatus] = None,
    ) -> List[ProfileRecord]:
        """List profiles with optional filters"""
        pass
    
    @abstractmethod
    async def add_metric(self, metric: MetricRecord) -> None:
        """Add a metric record"""
        pass
    
    @abstractmethod
    async def get_metrics(self, run_id: str) -> List[MetricRecord]:
        """Get all metrics for a profile run"""
        pass


class InMemoryDatabase(DatabaseInterface):
    """In-memory implementation of the database interface"""
    
    def __init__(self):
        self._profiles: Dict[str, ProfileRecord] = {}
        self._metrics: Dict[str, List[MetricRecord]] = {}
        self._lock = asyncio.Lock()
    
    async def create_profile(self, profile: ProfileRecord) -> ProfileRecord:
        """Create a new profile record"""
        async with self._lock:
            self._profiles[profile.run_id] = profile
            self._metrics[profile.run_id] = []
            return profile
    
    async def get_profile(self, run_id: str) -> Optional[ProfileRecord]:
        """Get a profile by ID"""
        return self._profiles.get(run_id)
    
    async def update_profile_status(
        self,
        run_id: str,
        status: ProfileStatus,
        error: Optional[str] = None,
    ) -> None:
        """Update profile status"""
        async with self._lock:
            if run_id in self._profiles:
                profile = self._profiles[run_id]
                profile.status = status
                
                if status == ProfileStatus.RUNNING and profile.started_at is None:
                    profile.started_at = datetime.utcnow()
                
                if status in (ProfileStatus.COMPLETED, ProfileStatus.FAILED, ProfileStatus.CANCELLED):
                    profile.completed_at = datetime.utcnow()
                
                if error:
                    profile.error = error
    
    async def list_profiles(
        self,
        queue_name: Optional[str] = None,
        status: Optional[ProfileStatus] = None,
    ) -> List[ProfileRecord]:
        """List profiles with optional filters"""
        profiles = list(self._profiles.values())
        
        if queue_name:
            profiles = [p for p in profiles if p.queue_name == queue_name]
        
        if status:
            profiles = [p for p in profiles if p.status == status]
        
        return sorted(profiles, key=lambda p: p.created_at, reverse=True)
    
    async def add_metric(self, metric: MetricRecord) -> None:
        """Add a metric record"""
        async with self._lock:
            if metric.run_id not in self._metrics:
                self._metrics[metric.run_id] = []
            self._metrics[metric.run_id].append(metric)
    
    async def get_metrics(self, run_id: str) -> List[MetricRecord]:
        """Get all metrics for a profile run"""
        return self._metrics.get(run_id, [])

