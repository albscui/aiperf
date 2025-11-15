#!/usr/bin/env python3
"""
Subscribe to real-time metrics from AIPerf.

Run this in a separate terminal after starting AIPerf with TCP enabled.

Usage:
    python subscribe_to_metrics.py [host] [port]
    
    Default: host=127.0.0.1, port=5664
"""

import asyncio
import json
import sys
from pprint import pprint

import zmq
import zmq.asyncio


async def subscribe_to_metrics(host: str = "127.0.0.1", port: int = 5664):
    """Subscribe to AIPerf real-time metrics."""
    
    # Create ZMQ context and subscriber socket
    context = zmq.asyncio.Context()
    socket = context.socket(zmq.SUB)
    
    # Connect to AIPerf event bus
    address = f"tcp://{host}:{port}"
    print("=" * 80)
    print("AIPerf Real-Time Metrics Subscriber")
    print("=" * 80)
    print(f"Connecting to: {address}")
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
    # Parse optional command line arguments
    host = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 5664
    
    asyncio.run(subscribe_to_metrics(host, port))

