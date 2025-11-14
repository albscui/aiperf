"""
AIPerf Executor Service

Responsible for launching and managing AIPerf profile runs.
"""

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from web.backend.storage import DatabaseInterface, ProfileStatus

logger = logging.getLogger(__name__)


class AIPerfExecutor:
    """Executes AIPerf profile runs"""

    def __init__(self, database: DatabaseInterface):
        self.database = database
        self._processes: Dict[str, asyncio.subprocess.Process] = {}
        self._monitor_tasks: Dict[str, asyncio.Task] = {}

    async def start_run(
        self,
        run_id: str,
        config: Dict[str, Any],
        zmq_host: str = "127.0.0.1",
        zmq_port: int = 5664,
        on_complete: Optional[Callable[[str, int], None]] = None,
    ) -> None:
        """
        Start an AIPerf profile run.

        Args:
            run_id: Unique ID for this run
            config: Configuration dictionary for the profile
            zmq_host: ZMQ host for metrics
            zmq_port: ZMQ backend port for metrics
            on_complete: Optional callback when run completes (run_id, exit_code)
        """
        if run_id in self._processes:
            raise ValueError(f"Run {run_id} is already running")

        logger.info(f"Starting AIPerf run {run_id}")

        # Build command
        cmd = self._build_aiperf_command(config, zmq_host, zmq_port)
        logger.info(f"Command: {' '.join(cmd)}")

        try:
            # Start subprocess
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            self._processes[run_id] = process

            # Update status to running
            await self.database.update_profile_status(run_id, ProfileStatus.RUNNING)

            # Monitor the process
            monitor_task = asyncio.create_task(
                self._monitor_process(run_id, process, on_complete)
            )
            self._monitor_tasks[run_id] = monitor_task

            logger.info(f"AIPerf run {run_id} started with PID {process.pid}")

        except Exception as e:
            logger.error(f"Failed to start AIPerf run {run_id}: {e}")
            await self.database.update_profile_status(
                run_id,
                ProfileStatus.FAILED,
                error=str(e),
            )
            raise

    async def stop_run(self, run_id: str) -> None:
        """Stop a running AIPerf profile"""
        if run_id not in self._processes:
            logger.warning(f"Run {run_id} is not running")
            return

        logger.info(f"Stopping AIPerf run {run_id}")

        process = self._processes[run_id]

        try:
            # Try graceful termination first
            process.terminate()

            # Wait up to 10 seconds
            try:
                await asyncio.wait_for(process.wait(), timeout=10.0)
            except asyncio.TimeoutError:
                # Force kill if it doesn't stop
                logger.warning(f"Force killing run {run_id}")
                process.kill()
                await process.wait()

            await self.database.update_profile_status(
                run_id,
                ProfileStatus.CANCELLED,
            )

        except Exception as e:
            logger.error(f"Error stopping run {run_id}: {e}")

    async def _monitor_process(
        self,
        run_id: str,
        process: asyncio.subprocess.Process,
        on_complete: Optional[Callable[[str, int], None]],
    ) -> None:
        """Monitor a running process and update status when complete"""
        try:
            # Wait for process to complete
            exit_code = await process.wait()

            # Capture output
            stdout, stderr = await process.communicate()

            logger.info(f"AIPerf run {run_id} completed with exit code {exit_code}")

            if stdout:
                logger.debug(f"Run {run_id} stdout: {stdout.decode()[:500]}")
            if stderr:
                logger.warning(f"Run {run_id} stderr: {stderr.decode()[:500]}")

            # Update status
            if exit_code == 0:
                await self.database.update_profile_status(
                    run_id,
                    ProfileStatus.COMPLETED,
                )
            else:
                error_msg = (
                    stderr.decode()[:1000] if stderr else f"Exit code: {exit_code}"
                )
                await self.database.update_profile_status(
                    run_id,
                    ProfileStatus.FAILED,
                    error=error_msg,
                )

            # Call completion callback
            if on_complete:
                try:
                    on_complete(run_id, exit_code)
                except Exception as e:
                    logger.error(f"Error in completion callback for {run_id}: {e}")

        except Exception as e:
            logger.error(f"Error monitoring process {run_id}: {e}")
            await self.database.update_profile_status(
                run_id,
                ProfileStatus.FAILED,
                error=str(e),
            )

        finally:
            # Clean up
            if run_id in self._processes:
                del self._processes[run_id]
            if run_id in self._monitor_tasks:
                del self._monitor_tasks[run_id]

    def _build_aiperf_command(
        self,
        config: Dict[str, Any],
        zmq_host: str,
        zmq_port: int,
    ) -> list[str]:
        """
        Build the AIPerf command from configuration.

        The command will be run using Python with the AIPerf module directly,
        similar to run_aiperf_with_tcp.py.
        """
        cmd = [
            # sys.executable,
            # "-m",
            "aiperf",
            "profile",
        ]

        # Add required arguments
        if config.get("model") is not None:
            cmd.extend(["-m", config.get("model")])

        if config.get("url") is not None:
            cmd.extend(["--url", config.get("url")])

        if config.get("endpoint_type") is not None:
            cmd.extend(["--endpoint-type", config.get("endpoint_type")])

        if config.get("endpoint") is not None:
            cmd.extend(["--custom-endpoint", config.get("endpoint")])

        if config.get("tokenizer") is not None:
            cmd.extend(["--tokenizer", config.get("tokenizer")])

        if config.get("request_count") is not None:
            cmd.extend(["--request-count", str(config.get("request_count"))])

        # Add optional arguments
        if config.get("concurrency") is not None:
            cmd.extend(["--concurrency", str(config.get("concurrency"))])

        if config.get("request_rate") is not None:
            cmd.extend(["--request-rate", str(config.get("request_rate"))])

        # Enable dashboard UI for real-time metrics
        cmd.extend(["--ui", "dashboard"])

        # Configure ZMQ host for metrics publishing
        cmd.extend(["--zmq-host", zmq_host])

        return cmd

    async def cleanup(self) -> None:
        """Stop all running processes"""
        logger.info("Cleaning up AIPerf executor")

        run_ids = list(self._processes.keys())

        for run_id in run_ids:
            await self.stop_run(run_id)

        # Wait for all monitor tasks to complete
        if self._monitor_tasks:
            await asyncio.gather(*self._monitor_tasks.values(), return_exceptions=True)

        logger.info("AIPerf executor cleanup complete")
