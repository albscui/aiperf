#!/usr/bin/env python3
"""
Run AIPerf with TCP ZMQ sockets enabled.

This allows external subscribers to connect and receive real-time metrics.

Usage:
    python run_aiperf_with_tcp.py \\
        -m "meta/llama-3.2-1b-instruct" \\
        --request-count 10 \\
        --url "https://nim.int.aire.nvidia.com/" \\
        --endpoint-type chat \\
        --custom-endpoint "v1/chat/completions" \\
        --tokenizer "meta-llama/Llama-3.2-1B-Instruct"
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from aiperf.cli import app
from aiperf.cli_runner import run_system_controller
from aiperf.common.config import ServiceConfig, ZMQTCPConfig
from aiperf.common.enums import AIPerfUIType


def main():
    """Run AIPerf with TCP ZMQ enabled."""
    
    # Parse command line arguments
    user_args = sys.argv[1:]
    
    if not user_args:
        print("Error: No arguments provided!")
        print("\nUsage:")
        print("  python run_aiperf_with_tcp.py [aiperf profile arguments]")
        print("\nExample:")
        print("  python run_aiperf_with_tcp.py \\")
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
        user_config = bound_arguments.arguments['user_config']
        print("✓ Configuration parsed successfully\n")
    except Exception as e:
        print(f"Error parsing configuration: {e}")
        sys.exit(1)
    
    # Configure ZMQ TCP
    zmq_tcp_config = ZMQTCPConfig(host="127.0.0.1")
    service_config = ServiceConfig(
        zmq_tcp=zmq_tcp_config,
        ui_type=AIPerfUIType.DASHBOARD,  # Required for real-time metrics
    )
    
    print("=" * 80)
    print("AIPerf with ZMQ TCP Enabled")
    print("=" * 80)
    print(f"Event bus backend (subscribers): {zmq_tcp_config.event_bus_proxy_config.backend_address}")
    print(f"Event bus frontend (publishers):  {zmq_tcp_config.event_bus_proxy_config.frontend_address}")
    print("\nIn another terminal, run:")
    print("  python subscribe_to_metrics.py")
    print("=" * 80 + "\n")
    
    # Run AIPerf
    try:
        run_system_controller(user_config, service_config)
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

