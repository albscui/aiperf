import asyncio
import subprocess

from web.backend.models.benchmark import BenchmarkRun

class AIPerfExecutor:
    """Executes aiperf profile runs via subprocess"""

    def __init__(self):
        self._processes: dict[str, subprocess.Popen] = {}
        self._monitor_tasks: dict[str, asyncio.Task] = {}
    
    async def start_run(self, run: BenchmarkRun, on_complete: callable | None = None) -> None:
        """Starts a new aiperf profile run"""

        cmd = self._build_aiperf_command(run)
