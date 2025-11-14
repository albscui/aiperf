# AIPerf Real-Time Metrics with ZMQ

This directory contains scripts for subscribing to real-time metrics from AIPerf using ZeroMQ (ZMQ) TCP sockets.

## Quick Start

### Terminal 1: Run AIPerf with TCP ZMQ

```bash
cd src/scratch

python run_aiperf_with_tcp.py \
    -m "meta/llama-3.2-1b-instruct" \
    --request-count 10 \
    --url "https://nim.int.aire.nvidia.com/" \
    --endpoint-type chat \
    --custom-endpoint "v1/chat/completions" \
    --tokenizer "meta-llama/Llama-3.2-1B-Instruct"
```

### Terminal 2: Subscribe to Metrics

```bash
cd src/scratch
python subscribe_to_metrics.py
```

You'll immediately start seeing real-time metrics as they're collected!

---

## System Architecture Overview

AIPerf uses a **distributed message-passing architecture** built on ZeroMQ (ZMQ) to enable real-time communication between components. Here's how it works:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           AIPerf System                                 │
│                                                                         │
│  ┌──────────────────┐         ┌─────────────────┐                     │
│  │ SystemController │         │  ProxyManager   │                     │
│  │                  │         │                 │                     │
│  │ - Orchestrates   │         │ Manages 3 ZMQ   │                     │
│  │   benchmark      │         │ Proxies:        │                     │
│  │ - Creates UI     │         │ • Event Bus     │                     │
│  │ - Manages        │         │ • Dataset Mgr   │                     │
│  │   services       │         │ • Raw Inference │                     │
│  └────────┬─────────┘         └────────┬────────┘                     │
│           │                            │                              │
│           │                            │                              │
│  ┌────────▼────────────────────────────▼──────────┐                   │
│  │                Services Layer                   │                   │
│  │  ┌──────────────┐  ┌──────────────┐           │                   │
│  │  │ Workers (N)  │  │ Timing Mgr   │           │                   │
│  │  │              │  │              │           │                   │
│  │  │ - Send HTTP  │  │ - Tracks     │           │                   │
│  │  │   requests   │  │   timing     │           │                   │
│  │  │ - Publish    │  │ - Manages    │           │                   │
│  │  │   records    │  │   phases     │           │                   │
│  │  └──────────────┘  └──────────────┘           │                   │
│  │                                                 │                   │
│  │  ┌──────────────────────────────────────────┐  │                   │
│  │  │      RecordsManager                      │  │                   │
│  │  │                                          │  │                   │
│  │  │ - Collects records from Workers          │  │                   │
│  │  │ - Processes with ResultsProcessors       │  │                   │
│  │  │ - Publishes real-time metrics every 0.5s │  │                   │
│  │  │   to Event Bus                           │  │                   │
│  │  └──────────────────────────────────────────┘  │                   │
│  └─────────────────────────────────────────────────┘                   │
│           │                                                            │
│           │ Publishes to Event Bus                                    │
│           ▼                                                            │
│  ┌──────────────────────────────────────────────────────┐             │
│  │            ZMQ Event Bus Proxy                       │             │
│  │            (XPUB/XSUB Pattern)                       │             │
│  │                                                      │             │
│  │  Frontend (XSUB): tcp://127.0.0.1:5663             │             │
│  │  Backend (XPUB):  tcp://127.0.0.1:5664             │             │
│  └──────────────────────────────────────────────────────┘             │
│           │                                                            │
└───────────┼────────────────────────────────────────────────────────────┘
            │
            │ External subscribers connect to backend (5664)
            ▼
   ┌─────────────────────┐
   │ Your Subscriber     │
   │ (subscribe_to_      │
   │  metrics.py)        │
   │                     │
   │ - Connects to 5664  │
   │ - Receives metrics  │
   │ - Displays data     │
   └─────────────────────┘
```

---

## Deep Dive: ZeroMQ Architecture

### What is ZeroMQ?

ZeroMQ (ZMQ) is a high-performance asynchronous messaging library that provides socket-like APIs for various messaging patterns. Unlike traditional message brokers (like RabbitMQ or Kafka), ZMQ is:

- **Brokerless**: No central server, messages flow directly between processes
- **Fast**: Extremely low latency (~10-20 microseconds)
- **Simple**: Socket-like API that's easy to use
- **Flexible**: Supports multiple transport protocols (TCP, IPC, inproc)

### ZMQ Proxy Pattern: XPUB/XSUB

AIPerf uses the **XPUB/XSUB proxy pattern** for the event bus. This enables **many-to-many** pub/sub communication:

```
Publishers (Many)          Proxy (One)         Subscribers (Many)
─────────────────         ─────────────        ──────────────────

┌─────────────┐                                ┌──────────────┐
│ Records     │──┐                          ┌─▶│ Dashboard UI │
│ Manager     │  │                          │  └──────────────┘
└─────────────┘  │                          │
                 │   ┌──────────────────┐   │  ┌──────────────┐
┌─────────────┐  │   │      PROXY       │   │  │ Your Custom  │
│ Timing      │──┼──▶│                  │───┼─▶│ Subscriber   │
│ Manager     │  │   │  ┌───┐    ┌───┐  │   │  └──────────────┘
└─────────────┘  │   │  │XSB│───▶│XPB│  │   │
                 │   │  │UB │    │UB │  │   │  ┌──────────────┐
┌─────────────┐  │   │  └───┘    └───┘  │   └─▶│ Monitoring   │
│ Workers     │──┘   │  5663      5664  │      │ System       │
│ (N nodes)   │      └──────────────────┘      └──────────────┘
└─────────────┘
    PUB                 Frontend Backend           SUB
                         (XSUB)   (XPUB)
```

#### How XPUB/XSUB Works

1. **XSUB (Frontend - Port 5663)**
   - Publishers connect here
   - Receives all published messages
   - Forwards subscription requests upstream

2. **XPUB (Backend - Port 5664)**  
   - Subscribers connect here
   - Broadcasts messages to matching subscribers
   - Handles subscription management

3. **The Proxy Loop**
   ```python
   zmq.proxy_steerable(
       frontend_socket,  # XSUB on 5663
       backend_socket,   # XPUB on 5664
       capture=None,     # Optional monitoring
       control=None      # Optional control
   )
   ```

#### Why This Pattern?

- **Decoupling**: Publishers and subscribers don't know about each other
- **Scalability**: Add/remove publishers and subscribers dynamically
- **Performance**: No message queuing or persistence overhead
- **Simplicity**: Single proxy handles all routing

### Topic-Based Filtering

ZMQ pub/sub uses **prefix-based topic filtering**:

```python
# Publisher sends: topic + message
await socket.send_multipart([b"realtime_metrics$", message_bytes])

# Subscriber filters by prefix
socket.setsockopt(zmq.SUBSCRIBE, b"realtime_metrics$")
```

**AIPerf Topic Convention**: Topics end with `$` to prevent accidental prefix matching:

- `realtime_metrics$` ✅ (Won't match `realtime_metrics_response$`)
- `realtime_metrics` ❌ (Would also match `realtime_metrics_anything`)

---

## AIPerf Internal Components

### 1. SystemController

The main orchestrator that:
- Parses configuration
- Creates and manages all services
- Initializes the ProxyManager
- Creates the UI (Dashboard, TQDM, or None)
- Coordinates the benchmark lifecycle

```python
class SystemController:
    def __init__(self, user_config, service_config):
        self.proxy_manager = ProxyManager(service_config)
        self.service_manager = ServiceManagerFactory.create_instance(...)
        self.ui = AIPerfUIFactory.create_instance(
            service_config.ui_type,  # DASHBOARD required for metrics!
            ...
        )
```

### 2. ProxyManager

Manages three ZMQ proxies:

```python
class ProxyManager:
    def __init__(self, service_config):
        self.proxies = [
            # Event Bus: Pub/Sub for events and metrics
            ZMQXPubXSubProxy(
                frontend=tcp://127.0.0.1:5663,
                backend=tcp://127.0.0.1:5664
            ),
            
            # Dataset Manager: Dealer/Router for request/reply
            ZMQDealerRouterProxy(
                frontend=tcp://127.0.0.1:5661,
                backend=tcp://127.0.0.1:5662
            ),
            
            # Raw Inference: Push/Pull for inference records
            ZMQPushPullProxy(
                frontend=tcp://127.0.0.1:5665,
                backend=tcp://127.0.0.1:5666
            )
        ]
```

Each proxy runs in its own thread via `zmq.proxy_steerable()`.

### 3. RecordsManager

The heart of metrics collection:

```python
class RecordsManager:
    def __init__(self, ...):
        # Results processors for each metric type
        self._metric_results_processors = [
            TimeToFirstTokenProcessor(),
            InterTokenLatencyProcessor(),
            RequestLatencyProcessor(),
            RequestThroughputProcessor(),
            TokenThroughputProcessor(),
            # ... more processors
        ]
    
    @background_task(interval=None, immediate=True)
    async def _report_realtime_inference_metrics_task(self):
        """Background task that publishes metrics every 0.5s"""
        if self.service_config.ui_type != AIPerfUIType.DASHBOARD:
            return  # Only publish with dashboard UI!
        
        while not self.stop_requested:
            await asyncio.sleep(Environment.UI.REALTIME_METRICS_INTERVAL)  # 0.5s
            
            # Check if new records were processed
            if self.processing_stats.total_records == self._previous_realtime_records:
                continue
            
            # Generate metrics from all processors
            await self._report_realtime_metrics()
```

#### Metrics Generation Flow

```
Worker completes request
    │
    ▼
Worker publishes MetricRecordsMessage via Push/Pull
    │
    ▼
RecordsManager receives via _on_metric_records()
    │
    ├─▶ Sends to each ResultsProcessor
    │   │
    │   ├─▶ TimeToFirstTokenProcessor.process_result()
    │   ├─▶ InterTokenLatencyProcessor.process_result()
    │   ├─▶ RequestLatencyProcessor.process_result()
    │   └─▶ ... (accumulates statistics)
    │
    ▼
Background task every 0.5s:
_report_realtime_inference_metrics_task()
    │
    ├─▶ Calls each processor.summarize()
    │   (generates MetricResult objects with avg, min, max, p50, p90, p99, etc.)
    │
    ├─▶ Creates RealtimeMetricsMessage
    │   message = {
    │       "message_type": "realtime_metrics",
    │       "service_id": "records_manager_xyz",
    │       "metrics": [MetricResult, MetricResult, ...]
    │   }
    │
    └─▶ Publishes to Event Bus
        await self.pub_client.publish(message)
```

### 4. MessageBusClientMixin

Provides pub/sub capabilities to any service:

```python
class MessageBusClientMixin:
    def __init__(self, service_config):
        # Create pub/sub clients
        self.sub_client = self.comms.create_sub_client(
            CommAddress.EVENT_BUS_PROXY_BACKEND  # Port 5664
        )
        self.pub_client = self.comms.create_pub_client(
            CommAddress.EVENT_BUS_PROXY_FRONTEND  # Port 5663
        )
    
    @on_init
    async def _setup_on_message_hooks(self):
        """Automatically subscribe to all @on_message hooks"""
        subscription_map = {}
        
        # Find all methods decorated with @on_message
        for hook in self.get_hooks(AIPerfHook.ON_MESSAGE):
            for message_type in hook.params:
                subscription_map.setdefault(message_type, []).append(hook.func)
        
        # Subscribe to all topics at once
        await self.sub_client.subscribe_all(subscription_map)
```

### 5. RealtimeMetricsMixin

Provides automatic subscription to metrics:

```python
@provides_hooks(AIPerfHook.ON_REALTIME_METRICS)
class RealtimeMetricsMixin(MessageBusClientMixin):
    """Mixin that subscribes to realtime_metrics$ topic"""
    
    @on_message(MessageType.REALTIME_METRICS)
    async def _on_realtime_metrics(self, message: RealtimeMetricsMessage):
        """Called automatically when metrics are received"""
        async with self._metrics_lock:
            self._metrics = message.metrics
        
        # Trigger all hooks registered for ON_REALTIME_METRICS
        await self.run_hooks(
            AIPerfHook.ON_REALTIME_METRICS,
            metrics=message.metrics
        )
```

The Dashboard UI inherits this mixin and implements:

```python
class AIPerfDashboardUI(RealtimeMetricsMixin, ...):
    @on_realtime_metrics
    async def _on_realtime_metrics(self, metrics: list[MetricResult]):
        """Update the UI with new metrics"""
        if self.realtime_metrics_dashboard:
            self.realtime_metrics_dashboard.update(metrics)
```

---

## Message Format

### RealtimeMetricsMessage

```json
{
  "message_type": "realtime_metrics",
  "service_id": "records_manager_abc123",
  "request_ns": 1699564829000000000,
  "metrics": [
    {
      "tag": "time_to_first_token",
      "header": "Time to First Token",
      "short_header": "TTFT",
      "unit": "ms",
      "display_unit": "ms",
      "current": 123.45,
      "count": 42,
      "avg": 120.50,
      "min": 95.20,
      "max": 180.30,
      "p50": 118.70,
      "p90": 150.20,
      "p95": 165.80,
      "p99": 175.10,
      "std": 15.20
    },
    {
      "tag": "request_latency",
      "header": "Request Latency",
      "unit": "ms",
      "current": 1245.67,
      "count": 42,
      "avg": 1230.00,
      "min": 980.00,
      "max": 1450.00,
      "p50": 1210.00,
      "p90": 1380.00,
      "p99": 1420.00
    }
  ]
}
```

### Available Metrics

| Tag | Description | Unit |
|-----|-------------|------|
| `time_to_first_token` | Time from request to first token | ms |
| `inter_token_latency` | Average time between tokens | ms |
| `request_latency` | Total request duration | ms |
| `request_throughput` | Requests completed per second | req/s |
| `token_throughput_total` | Total tokens per second | tokens/s |
| `output_token_throughput` | Output tokens per second | tokens/s |
| `input_token_count` | Input tokens per request | tokens |
| `output_token_count` | Output tokens per request | tokens |

---

## ZMQ Communication Patterns in AIPerf

AIPerf uses three ZMQ patterns:

### 1. PUB/SUB (Event Bus)

**Use Case**: Broadcasting events and metrics

```
Publishers (RecordsManager, TimingManager, Workers)
    │
    ▼
XPUB/XSUB Proxy (tcp://127.0.0.1:5663/5664)
    │
    ▼
Subscribers (UI, External monitors)
```

**Messages**:
- `realtime_metrics$` - Inference metrics
- `realtime_telemetry_metrics$` - GPU metrics
- `worker_health$` - Worker status updates
- `records_processing_stats$` - Processing progress

### 2. DEALER/ROUTER (Dataset Manager)

**Use Case**: Request/Reply with load balancing

```
Workers (DEALER) ←→ DEALER/ROUTER Proxy ←→ Dataset Manager (ROUTER)
```

**Purpose**: Workers request data samples, Dataset Manager responds

### 3. PUSH/PULL (Raw Inference)

**Use Case**: High-throughput one-way data flow

```
Workers (PUSH) → PUSH/PULL Proxy → RecordsManager (PULL)
```

**Purpose**: Workers push completed request records to RecordsManager

---

## Configuration Deep Dive

### ZMQTCPConfig

```python
class ZMQTCPConfig:
    host: str = "127.0.0.1"
    
    # Event Bus Proxy (PUB/SUB)
    event_bus_proxy_config = ZMQTCPProxyConfig(
        frontend_port=5663,  # Publishers connect here
        backend_port=5664,   # Subscribers connect here
    )
    
    # Dataset Manager Proxy (DEALER/ROUTER)
    dataset_manager_proxy_config = ZMQTCPProxyConfig(
        frontend_port=5661,
        backend_port=5662,
    )
    
    # Raw Inference Proxy (PUSH/PULL)
    raw_inference_proxy_config = ZMQTCPProxyConfig(
        frontend_port=5665,
        backend_port=5666,
    )
    
    # Direct connections (no proxy)
    records_push_pull_port: int = 5557
    credit_drop_port: int = 5562
    credit_return_port: int = 5563
```

### ServiceConfig

```python
service_config = ServiceConfig(
    zmq_tcp=ZMQTCPConfig(host="127.0.0.1"),
    ui_type=AIPerfUIType.DASHBOARD,  # CRITICAL: Required for metrics!
)
```

**Why `ui_type=DASHBOARD`?**

The RecordsManager only publishes metrics when the UI type is DASHBOARD:

```python
if self.service_config.ui_type != AIPerfUIType.DASHBOARD:
    return  # Don't publish metrics!
```

This is because:
- Metrics publishing adds overhead
- Simple UI (TQDM) doesn't need real-time updates
- No UI means no one is listening

---

## Creating Your Own Subscriber

### Basic Pattern

```python
import asyncio
import json
import zmq.asyncio

async def my_subscriber():
    context = zmq.asyncio.Context()
    socket = context.socket(zmq.SUB)
    
    # Connect to backend (subscribers port)
    socket.connect("tcp://127.0.0.1:5664")
    
    # Subscribe to topics
    socket.setsockopt(zmq.SUBSCRIBE, b"realtime_metrics$")
    
    while True:
        topic, data = await socket.recv_multipart()
        message = json.loads(data)
        
        # Process metrics
        for metric in message.get("metrics", []):
            print(f"{metric['tag']}: {metric['current']}")

asyncio.run(my_subscriber())
```

### Advanced: Using AIPerf Mixins

```python
from aiperf.common.mixins import RealtimeMetricsMixin
from aiperf.common.hooks import on_realtime_metrics
from aiperf.common.models import MetricResult

class MySubscriber(RealtimeMetricsMixin):
    def __init__(self, service_config):
        super().__init__(service_config=service_config)
    
    @on_realtime_metrics
    async def _on_metrics(self, metrics: list[MetricResult]):
        # Automatic subscription and parsing!
        for metric in metrics:
            print(f"{metric.header}: {metric.current} {metric.unit}")
            
            # Access statistics
            print(f"  P99: {metric.p99}")
            print(f"  Avg: {metric.avg}")
```

---

## Troubleshooting

### No Metrics Received

**Symptoms**: Subscriber connects but never receives messages

**Checklist**:
1. ✅ Is AIPerf running with `ui_type=DASHBOARD`?
2. ✅ Are you connecting to port **5664** (backend)?
3. ✅ Is the topic correct: `b"realtime_metrics$"`?
4. ✅ Have requests been processed? (Metrics only publish when there's data)

### Port Already in Use

```
OSError: Address already in use
```

**Solution**: 
```bash
# Find process using port 5664
lsof -i :5664

# Kill the process
kill -9 <PID>
```

### Subscription Not Working

**Wrong**: Connect to frontend (5663)
```python
socket.connect("tcp://127.0.0.1:5663")  # ❌ This is for publishers!
```

**Correct**: Connect to backend (5664)
```python
socket.connect("tcp://127.0.0.1:5664")  # ✅ This is for subscribers!
```

### Messages Delayed

ZMQ has a "slow joiner" problem - messages sent before a subscriber connects are lost.

**Solution**:
```python
socket.connect("tcp://127.0.0.1:5664")
socket.setsockopt(zmq.SUBSCRIBE, b"realtime_metrics$")
await asyncio.sleep(0.1)  # Give time for subscription to propagate
```

---

## Advanced Topics

### Multiple Subscribers

Run as many as you want - they all receive the same messages:

```bash
# Terminal 1: AIPerf
python run_aiperf_with_tcp.py [args...]

# Terminal 2: Display metrics
python subscribe_to_metrics.py

# Terminal 3: Log to file
python log_metrics.py

# Terminal 4: Send to Prometheus
python prometheus_exporter.py
```

### Remote Monitoring

Change host to `0.0.0.0` to allow external connections:

```python
zmq_tcp_config = ZMQTCPConfig(host="0.0.0.0")
```

Then connect from another machine:
```bash
python subscribe_to_metrics.py 192.168.1.100 5664
```

### Filtering Metrics

```python
for metric in message.get("metrics", []):
    # Only show TTFT
    if metric.get("tag") == "time_to_first_token":
        print(f"TTFT: {metric['current']} ms")
    
    # Only show P99 latencies
    if "latency" in metric.get("tag", ""):
        print(f"{metric['tag']} P99: {metric.get('p99')}")
```

### Saving to Database

```python
import sqlite3

async def save_to_db(metrics):
    conn = sqlite3.connect("metrics.db")
    for metric in metrics:
        conn.execute(
            "INSERT INTO metrics (timestamp, tag, value) VALUES (?, ?, ?)",
            (time.time(), metric["tag"], metric["current"])
        )
    conn.commit()
```

---

## Key Takeaways

1. **ZMQ Proxies**: AIPerf uses XPUB/XSUB proxy for many-to-many pub/sub
2. **Port 5664**: Subscribers connect to the backend (XPUB)
3. **Dashboard UI Required**: `ui_type=DASHBOARD` enables metrics publishing
4. **Topic Suffix**: All topics end with `$` for exact matching
5. **Metrics Every 0.5s**: RecordsManager publishes updates twice per second
6. **Decoupled Design**: Publishers and subscribers are completely independent
7. **Multiple Patterns**: AIPerf uses PUB/SUB, DEALER/ROUTER, and PUSH/PULL

## Further Reading

- ZeroMQ Guide: https://zguide.zeromq.org/
- AIPerf Source Code:
  - `src/aiperf/zmq/` - ZMQ implementations
  - `src/aiperf/records/records_manager.py` - Metrics publishing
  - `src/aiperf/common/mixins/realtime_metrics_mixin.py` - Subscription helper
  - `src/aiperf/controller/proxy_manager.py` - Proxy orchestration

---

## License

Same as AIPerf: Apache 2.0

