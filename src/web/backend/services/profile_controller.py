"""
Profile Controller

Manages the queue of AIPerf profile runs and orchestrates execution.
"""

import asyncio
import logging
from collections import defaultdict
from typing import Any, Dict

from web.backend.services.aiperf_executor import AIPerfExecutor
from web.backend.services.metrics_subscriber import MetricsSubscriber
from web.backend.services.port_allocator import PortAllocator
from web.backend.storage import DatabaseInterface, ProfileRecord, ProfileStatus

logger = logging.getLogger(__name__)


class ProfileController:
    """
    Controller for managing AIPerf profile runs.

    Implements a queue-based execution model where jobs in each queue
    are processed sequentially (one at a time per queue).
    """

    def __init__(self, database: DatabaseInterface):
        self.database = database
        self.executor = AIPerfExecutor(database)
        self.subscriber = MetricsSubscriber(database)
        # self.port_allocator = PortAllocator()

        # Queue management
        self._queues: Dict[str, asyncio.Queue] = defaultdict(asyncio.Queue)
        self._queue_tasks: Dict[str, asyncio.Task] = {}
        self._running = False

    async def start(self) -> None:
        """Start the controller"""
        if self._running:
            return

        self._running = True
        logger.info("Profile controller started")

    async def stop(self) -> None:
        """Stop the controller and clean up"""
        if not self._running:
            return

        self._running = False
        logger.info("Stopping profile controller")

        # Stop all queue processing tasks
        for queue_name, task in self._queue_tasks.items():
            logger.info(f"Stopping queue processor for '{queue_name}'")
            task.cancel()

        # Wait for all tasks to complete
        if self._queue_tasks:
            await asyncio.gather(*self._queue_tasks.values(), return_exceptions=True)

        # Clean up executor and subscriber
        await self.executor.cleanup()
        await self.subscriber.stop_all()

        logger.info("Profile controller stopped")

    async def submit_profile(
        self,
        queue_name: str,
        config: Dict[str, Any],
    ) -> ProfileRecord:
        """
        Submit a new profile run to the queue.

        Args:
            queue_name: Name of the queue to submit to
            config: Configuration for the AIPerf profile

        Returns:
            ProfileRecord: The created profile record
        """
        # Create profile record
        profile = ProfileRecord(
            run_id=self._generate_run_id(),
            queue_name=queue_name,
            config=config,
            status=ProfileStatus.PENDING,
        )

        # Save to database
        await self.database.create_profile(profile)

        logger.info(f"Submitted profile {profile.run_id} to queue '{queue_name}'")

        # Add to queue
        queue = self._queues[queue_name]
        await queue.put(profile.run_id)

        # Start queue processor if not already running
        if queue_name not in self._queue_tasks:
            task = asyncio.create_task(self._process_queue(queue_name))
            self._queue_tasks[queue_name] = task

        return profile

    async def _process_queue(self, queue_name: str) -> None:
        """
        Process jobs from a specific queue.

        Jobs are processed sequentially - one at a time.
        """
        logger.info(f"Started queue processor for '{queue_name}'")
        queue = self._queues[queue_name]

        try:
            while self._running:
                try:
                    # Wait for next job (with timeout to check _running flag)
                    try:
                        run_id = await asyncio.wait_for(queue.get(), timeout=1.0)
                    except asyncio.TimeoutError:
                        continue

                    # Process the job
                    await self._execute_profile(run_id)

                    # Mark task done
                    queue.task_done()

                except asyncio.CancelledError:
                    logger.info(f"Queue processor for '{queue_name}' cancelled")
                    break
                except Exception as e:
                    logger.error(f"Error processing queue '{queue_name}': {e}")

        finally:
            logger.info(f"Queue processor for '{queue_name}' stopped")

    async def _execute_profile(self, run_id: str) -> None:
        """
        Execute a single profile run.

        This orchestrates:
        1. Allocating ZMQ ports
        2. Starting the metrics subscriber
        3. Starting the AIPerf executor
        4. Waiting for completion
        5. Cleaning up resources
        """
        logger.info(f"Executing profile {run_id}")

        # Get profile from database
        profile = await self.database.get_profile(run_id)
        if not profile:
            logger.error(f"Profile {run_id} not found in database")
            return

        try:
            # Allocate ZMQ ports
            # ports = await self.port_allocator.allocate_ports(run_id)
            port = 5664
            logger.info(f"Allocated ports for {run_id}: backend={port}")

            # Start metrics subscriber
            await self.subscriber.subscribe_to_run(
                run_id=run_id,
                host="127.0.0.1",
                port=port,
            )

            # Define completion callback
            def on_complete(completed_run_id: str, exit_code: int):
                """Called when the profile completes"""
                logger.info(
                    f"Profile {completed_run_id} completed with exit code {exit_code}"
                )

                # Schedule cleanup
                asyncio.create_task(self._cleanup_profile(completed_run_id))

            # Start AIPerf executor
            await self.executor.start_run(
                run_id=run_id,
                config=profile.config,
                zmq_host="127.0.0.1",
                zmq_port=port,
                on_complete=on_complete,
            )

            # Wait for the process to complete
            # The executor will update the status when done
            while True:
                print("Waiting for profile to complete")
                profile = await self.database.get_profile(run_id)
                if profile and profile.status in (
                    ProfileStatus.COMPLETED,
                    ProfileStatus.FAILED,
                    ProfileStatus.CANCELLED,
                ):
                    break
                await asyncio.sleep(1.0)

            logger.info(
                f"Profile {run_id} finished with status: {profile.status.value}"
            )

        except Exception as e:
            logger.error(f"Error executing profile {run_id}: {e}")
            await self.database.update_profile_status(
                run_id,
                ProfileStatus.FAILED,
                error=str(e),
            )
            await self._cleanup_profile(run_id)

    async def _cleanup_profile(self, run_id: str) -> None:
        """Clean up resources for a completed profile"""
        logger.info(f"Cleaning up profile {run_id}")

        try:
            # Stop metrics subscriber
            await self.subscriber.unsubscribe_from_run(run_id)

            # Release ports
            # await self.port_allocator.release_ports(run_id)

            logger.info(f"Cleanup complete for profile {run_id}")

        except Exception as e:
            logger.error(f"Error cleaning up profile {run_id}: {e}")

    def _generate_run_id(self) -> str:
        """Generate a unique run ID"""
        from uuid import uuid4

        return str(uuid4())
