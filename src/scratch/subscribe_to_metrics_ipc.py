#!/usr/bin/env python3
"""
Subscribe to real-time metrics from AIPerf using IPC.

Run this in a separate terminal after starting AIPerf with IPC enabled.
IPC sockets must be on the same machine (local only).

Usage:
    python subscribe_to_metrics_ipc.py [socket_path]

    Default socket_path: /tmp/aiperf_ipc_sockets/event_bus_proxy_backend.ipc
"""

import asyncio
import json
import sys
from pathlib import Path
from pprint import pprint

import zmq
import zmq.asyncio


async def subscribe_to_metrics_ipc(socket_path: Path):
    """Subscribe to AIPerf real-time metrics via IPC."""

    # Create ZMQ context and subscriber socket
    context = zmq.asyncio.Context()
    socket = context.socket(zmq.SUB)

    # Connect to AIPerf event bus via IPC
    address = f"ipc://{socket_path}"
    print("=" * 80)
    print("AIPerf Real-Time Metrics Subscriber (IPC)")
    print("=" * 80)
    print(f"Connecting to: {address}")

    if not socket_path.exists():
        print(f"\n⚠️  Warning: Socket file does not exist yet: {socket_path}")
        print("Make sure AIPerf is running with IPC enabled first.\n")

    socket.connect(address)

    # Subscribe to metrics topics
    # Note: AIPerf topics end with '$' to prevent prefix matching
    socket.setsockopt(zmq.SUBSCRIBE, b"realtime_metrics$")
    socket.setsockopt(zmq.SUBSCRIBE, b"realtime_telemetry_metrics$")

    print("Subscribed to:")
    print("  - realtime_metrics$")
    print("  - realtime_telemetry_metrics$")
    print("\nWaiting for metrics... (Press Ctrl+C to exit)\n")

    update_count = 0

    try:
        while True:
            # Receive message: [topic, data]
            topic_bytes, message_bytes = await socket.recv_multipart()

            # Parse message
            topic = topic_bytes.decode().rstrip("$")
            message = json.loads(message_bytes)

            update_count += 1

            # Display metrics
            print("=" * 80)
            print(f"UPDATE #{update_count} - {topic}")
            print("=" * 80)

            pprint(message, indent=4)
            print("=" * 80 + "\n")

    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        socket.close()
        context.term()
        print("Done!")


if __name__ == "__main__":
    # Parse optional command line argument for socket path
    if len(sys.argv) > 1:
        socket_path = Path(sys.argv[1])
    else:
        # Default to the backend socket where subscribers connect
        socket_path = Path("/tmp/aiperf_ipc_sockets/event_bus_proxy_backend.ipc")

    asyncio.run(subscribe_to_metrics_ipc(socket_path))
