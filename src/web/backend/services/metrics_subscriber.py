"""
ZMQ Metrics Subscriber Service

Subscribes to real-time metrics from AIPerf via ZMQ TCP socket
and stores them in the database.
"""

import asyncio
import json
import logging
from typing import Optional

import zmq
import zmq.asyncio

from web.backend.storage import DatabaseInterface, MetricRecord

logger = logging.getLogger(__name__)


class MetricsSubscriber:
    """Subscribes to AIPerf real-time metrics via ZMQ"""

    def __init__(self, database: DatabaseInterface):
        self.database = database
        self.context: Optional[zmq.asyncio.Context] = None
        self.socket: Optional[zmq.asyncio.Socket] = None
        self._subscriptions: dict[str, asyncio.Task] = {}
        self._stop_events: dict[str, asyncio.Event] = {}

    async def subscribe_to_run(
        self,
        run_id: str,
        host: str = "127.0.0.1",
        port: int = 5664,
    ) -> None:
        """
        Start subscribing to metrics for a specific run.

        Args:
            run_id: The unique ID of the profile run
            host: ZMQ host to connect to
            port: ZMQ port to connect to (event bus backend port)
        """
        if run_id in self._subscriptions:
            logger.warning(f"Already subscribing to metrics for run {run_id}")
            return

        logger.info(f"Starting metrics subscription for run {run_id} at {host}:{port}")

        # Create stop event for this subscription
        stop_event = asyncio.Event()
        self._stop_events[run_id] = stop_event

        # Start subscription task
        task = asyncio.create_task(self._subscribe_loop(run_id, host, port, stop_event))
        self._subscriptions[run_id] = task

    async def unsubscribe_from_run(self, run_id: str) -> None:
        """Stop subscribing to metrics for a specific run"""
        if run_id not in self._subscriptions:
            return

        logger.info(f"Stopping metrics subscription for run {run_id}")

        # Signal the subscription to stop
        if run_id in self._stop_events:
            self._stop_events[run_id].set()

        # Wait for the task to complete
        task = self._subscriptions.pop(run_id)
        try:
            await asyncio.wait_for(task, timeout=5.0)
        except asyncio.TimeoutError:
            logger.warning(f"Timeout waiting for subscription {run_id} to stop")
            task.cancel()

        # Clean up
        if run_id in self._stop_events:
            del self._stop_events[run_id]

    async def _subscribe_loop(
        self,
        run_id: str,
        host: str,
        port: int,
        stop_event: asyncio.Event,
    ) -> None:
        """Main subscription loop for a specific run"""
        context = None
        socket = None

        try:
            # Create ZMQ context and subscriber socket
            context = zmq.asyncio.Context()
            socket = context.socket(zmq.SUB)

            # Connect to AIPerf event bus
            address = f"tcp://{host}:{port}"
            socket.connect(address)

            # Subscribe to metrics topics
            # Note: AIPerf topics end with '$' to prevent prefix matching
            socket.setsockopt(zmq.SUBSCRIBE, b"realtime_metrics$")
            socket.setsockopt(zmq.SUBSCRIBE, b"realtime_telemetry_metrics$")

            # Set receive timeout so we can check stop_event periodically
            socket.setsockopt(zmq.RCVTIMEO, 1000)  # 1 second timeout

            logger.info(f"Connected to {address} for run {run_id}")
            logger.info(
                f"Subscribed to: realtime_metrics$, realtime_telemetry_metrics$"
            )

            update_count = 0

            while not stop_event.is_set():
                try:
                    print("Receiving message")
                    # Try to receive message: [topic, data]
                    topic_bytes, message_bytes = await socket.recv_multipart()

                    # Parse message
                    topic = topic_bytes.decode().rstrip("$")
                    data = json.loads(message_bytes)

                    update_count += 1

                    # Store metric in database
                    metric = MetricRecord(
                        run_id=run_id,
                        topic=topic,
                        data=data,
                    )
                    await self.database.add_metric(metric)

                    logger.debug(
                        f"Stored metric #{update_count} for run {run_id}: {topic}"
                    )

                except zmq.Again:
                    # Timeout - continue to check stop_event
                    continue
                except Exception as e:
                    logger.error(f"Error processing metric for run {run_id}: {e}")

            logger.info(
                f"Subscription stopped for run {run_id}. Total metrics: {update_count}"
            )

        except Exception as e:
            logger.error(f"Error in subscription loop for run {run_id}: {e}")

        finally:
            # Clean up
            if socket:
                socket.close()
            if context:
                context.term()

    async def stop_all(self) -> None:
        """Stop all active subscriptions"""
        logger.info("Stopping all metrics subscriptions")

        # Get all run IDs
        run_ids = list(self._subscriptions.keys())

        # Stop each subscription
        for run_id in run_ids:
            await self.unsubscribe_from_run(run_id)

        logger.info("All subscriptions stopped")
