# Quick Start Guide

Get up and running with the AIPerf FastAPI backend in 5 minutes.

## Prerequisites

- Python 3.12+
- AIPerf installed (in the same environment)
- Access to an inference endpoint (e.g., NIM)

## Step 1: Install Dependencies

```bash
cd /Users/albcui/nv/aiperf/src/web/backend
pip install -r requirements.txt
```

## Step 2: Start the Server

```bash
# From the src directory
cd /Users/albcui/nv/aiperf/src

# Start the server
python -m uvicorn web.backend.main:app --host 0.0.0.0 --port 8000 --reload
```

You should see:

```
INFO:     Started server process [12345]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

## Step 3: Test the API

### Option A: Use the test client

```bash
# In another terminal
cd /Users/albcui/nv/aiperf/src
python web/backend/test_client.py
```

### Option B: Use curl

```bash
# Create a profile
curl -X POST http://localhost:8000/aiperf/profiles \
  -H "Content-Type: application/json" \
  -d '{
    "queue_name": "default",
    "config": {
      "model": "meta/llama-3.2-1b-instruct",
      "url": "https://nim.int.aire.nvidia.com/",
      "endpoint_type": "chat",
      "endpoint": "v1/chat/completions",
      "tokenizer": "meta-llama/Llama-3.2-1B-Instruct",
      "request_count": 10
    }
  }'

# Save the run_id from the response, then:

# Check status
curl http://localhost:8000/aiperf/profiles/{run_id}

# Get metrics
curl http://localhost:8000/aiperf/profiles/{run_id}/metrics
```

### Option C: Use the interactive docs

Visit http://localhost:8000/docs in your browser for Swagger UI.

## Step 4: Monitor Your Job

Watch the server logs to see:

- Job submission
- Queue processing
- AIPerf execution
- Metrics collection
- Job completion

Example log output:

```
INFO:web.backend.services.profile_controller:Submitted profile abc-123 to queue 'default'
INFO:web.backend.services.profile_controller:Executing profile abc-123
INFO:web.backend.services.metrics_subscriber:Starting metrics subscription for run abc-123
INFO:web.backend.services.aiperf_executor:Starting AIPerf run abc-123
INFO:web.backend.services.aiperf_executor:AIPerf run abc-123 started with PID 12346
INFO:web.backend.services.metrics_subscriber:Connected to tcp://127.0.0.1:5664 for run abc-123
INFO:web.backend.services.profile_controller:Profile abc-123 finished with status: completed
```

## What Just Happened?

1. **Job Created**: Your profile configuration was saved to the database with a unique ID
2. **Queued**: The job was added to the "default" queue
3. **Executed**: The queue processor started your job when resources were available
4. **Monitored**: Real-time metrics were collected via ZMQ and stored
5. **Completed**: The job finished and resources were cleaned up

## Next Steps

- Read [README.md](README.md) for detailed API documentation
- Read [ARCHITECTURE.md](ARCHITECTURE.md) to understand the system design
- Modify the test client to run your own benchmarks
- Integrate with your existing tools via the REST API

## Troubleshooting

### Server won't start

**Error**: `ModuleNotFoundError: No module named 'fastapi'`

**Fix**:
```bash
pip install -r requirements.txt
```

### Jobs stay in "pending"

**Check**: Is the server running? Check logs for errors.

**Fix**: Restart the server.

### No metrics received

**Check**: Is AIPerf configured correctly? Can it reach the inference endpoint?

**Fix**: Check the AIPerf logs in the server output.

### Port conflicts

**Error**: `Address already in use`

**Fix**: 
- Stop other services using port 8000, or
- Use a different port: `uvicorn web.backend.main:app --port 8001`

## Example: Python Integration

```python
import requests
import time

# Create a profile
response = requests.post(
    "http://localhost:8000/aiperf/profiles",
    json={
        "queue_name": "default",
        "config": {
            "model": "meta/llama-3.2-1b-instruct",
            "url": "https://nim.int.aire.nvidia.com/",
            "endpoint_type": "chat",
            "endpoint": "v1/chat/completions",
            "tokenizer": "meta-llama/Llama-3.2-1B-Instruct",
            "request_count": 10,
        }
    }
)

run_id = response.json()["run_id"]
print(f"Created profile: {run_id}")

# Wait for completion
while True:
    status_response = requests.get(
        f"http://localhost:8000/aiperf/profiles/{run_id}"
    )
    status = status_response.json()["status"]
    
    print(f"Status: {status}")
    
    if status in ["completed", "failed", "cancelled"]:
        break
    
    time.sleep(2)

# Get metrics
metrics_response = requests.get(
    f"http://localhost:8000/aiperf/profiles/{run_id}/metrics"
)
metrics = metrics_response.json()

print(f"Total metrics collected: {metrics['total_count']}")
print(f"Topics: {metrics['topics']}")

# Analyze metrics
for metric in metrics['metrics']:
    if metric['topic'] == 'realtime_metrics':
        print(f"Metric at {metric['timestamp']}:")
        print(f"  Data: {metric['data']}")
```

## Support

- Check the logs for error messages
- Review the [ARCHITECTURE.md](ARCHITECTURE.md) for system design
- Review the [README.md](README.md) for API documentation

