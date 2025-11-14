#!/usr/bin/env python3
"""
Run AIPerf with IPC ZMQ sockets enabled.

This uses Unix domain sockets for inter-process communication on the same machine.
IPC is faster than TCP but only works for processes on the same host.

Usage:
    python run_aiperf_with_ipc.py \\
        -m "meta/llama-3.2-1b-instruct" \\
        --request-count 10 \\
        --url "https://nim.int.aire.nvidia.com/" \\
        --endpoint-type chat \\
        --custom-endpoint "v1/chat/completions" \\
        --tokenizer "meta-llama/Llama-3.2-1B-Instruct"
"""

import sys
import tempfile
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from aiperf.cli import app
from aiperf.cli_runner import run_system_controller
from aiperf.common.config import ServiceConfig, ZMQIPCConfig
from aiperf.common.enums import AIPerfUIType


def main():
    """Run AIPerf with IPC ZMQ enabled."""

    # Parse command line arguments
    user_args = sys.argv[1:]

    if not user_args:
        print("Error: No arguments provided!")
        print("\nUsage:")
        print("  python run_aiperf_with_ipc.py [aiperf profile arguments]")
        print("\nExample:")
        print("  python run_aiperf_with_ipc.py \\")
        print("    -m 'meta/llama-3.2-1b-instruct' \\")
        print("    --request-count 10 \\")
        print("    --url 'https://nim.int.aire.nvidia.com/' \\")
        print("    --endpoint-type chat \\")
        print("    --custom-endpoint 'v1/chat/completions' \\")
        print("    --tokenizer 'meta-llama/Llama-3.2-1B-Instruct'")
        sys.exit(1)

    # Parse user config using AIPerf's CLI
    try:
        command, bound_arguments, _ = app.parse_args(["profile"] + user_args)
        user_config = bound_arguments.arguments["user_config"]
        print("✓ Configuration parsed successfully\n")
    except Exception as e:
        print(f"Error parsing configuration: {e}")
        sys.exit(1)

    # Configure ZMQ IPC with a custom socket directory
    try:
        tmp_dir = tempfile.mkdtemp()
        socket_path = Path(tmp_dir) / "aiperf-sockets"
        print(f"Socket directory: {socket_path.resolve()}")
        zmq_ipc_config = ZMQIPCConfig(path=socket_path)
        service_config = ServiceConfig(
            zmq_ipc=zmq_ipc_config,
            ui_type=AIPerfUIType.DASHBOARD,  # Required for real-time metrics
        )
        print("✓ Service configuration created successfully\n")
    except Exception as e:
        print(f"Error creating service configuration: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)

    print("=" * 80)
    print("AIPerf with ZMQ IPC Enabled")
    print("=" * 80)
    print(f"Socket directory: {socket_path}")
    print(
        f"Event bus backend (subscribers): {zmq_ipc_config.event_bus_proxy_config.backend_address}"
    )
    print(
        f"Event bus frontend (publishers):  {zmq_ipc_config.event_bus_proxy_config.frontend_address}"
    )
    print("\nNote: IPC sockets are local only (same machine)")
    print("IPC is faster than TCP but cannot be accessed remotely")
    print("=" * 80 + "\n")

    # Run AIPerf
    print("Starting AIPerf System Controller...")
    try:
        run_system_controller(user_config, service_config)
        print("\nAIPerf System Controller completed successfully")
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n\nError: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
