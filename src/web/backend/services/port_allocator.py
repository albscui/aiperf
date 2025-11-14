# services/port_allocator.py
import asyncio
from typing import Optional, Set

from web.backend.models.benchmark import ZMQPortAllocation


class PortAllocator:
    """Manages ZMQ port allocation from a reserved pool"""
    
    # Reserve ports 6000-6999 for ZMQ (1000 ports = ~111 concurrent runs)
    PORT_POOL_START = 6000
    PORT_POOL_END = 6999
    PORTS_PER_RUN = 9  # Number of ports needed per aiperf run
    
    def __init__(self):
        self._lock = asyncio.Lock()
        self._allocated_ports: Set[int] = set()
        self._port_assignments: dict[str, ZMQPortAllocation] = {}
    
    async def allocate_ports(self, run_id: str) -> ZMQPortAllocation:
        """Allocate a block of ports for a benchmark run"""
        async with self._lock:
            # Find a contiguous block of available ports
            base_port = self._find_available_block()
            
            if base_port is None:
                raise RuntimeError("No available ports in pool")
            
            # Allocate the ports
            allocation = ZMQPortAllocation(
                event_bus_frontend=base_port,
                event_bus_backend=base_port + 1,
                dataset_frontend=base_port + 2,
                dataset_backend=base_port + 3,
                raw_inference_frontend=base_port + 4,
                raw_inference_backend=base_port + 5,
                records_port=base_port + 6,
                credit_drop_port=base_port + 7,
                credit_return_port=base_port + 8,
            )
            
            # Mark ports as allocated
            for port in range(base_port, base_port + self.PORTS_PER_RUN):
                self._allocated_ports.add(port)
            
            self._port_assignments[run_id] = allocation
            return allocation
    
    async def release_ports(self, run_id: str) -> None:
        """Release ports back to the pool"""
        async with self._lock:
            if run_id not in self._port_assignments:
                return
            
            allocation = self._port_assignments[run_id]
            
            # Release all ports
            for port in [
                allocation.event_bus_frontend,
                allocation.event_bus_backend,
                allocation.dataset_frontend,
                allocation.dataset_backend,
                allocation.raw_inference_frontend,
                allocation.raw_inference_backend,
                allocation.records_port,
                allocation.credit_drop_port,
                allocation.credit_return_port,
            ]:
                self._allocated_ports.discard(port)
            
            del self._port_assignments[run_id]
    
    def _find_available_block(self) -> Optional[int]:
        """Find a contiguous block of PORTS_PER_RUN available ports"""
        for base_port in range(self.PORT_POOL_START, self.PORT_POOL_END - self.PORTS_PER_RUN):
            # Check if all ports in this block are available
            if all(
                port not in self._allocated_ports 
                for port in range(base_port, base_port + self.PORTS_PER_RUN)
            ):
                return base_port
        return None
    
    def get_allocation(self, run_id: str) -> Optional[ZMQPortAllocation]:
        """Get port allocation for a run"""
        return self._port_assignments.get(run_id)