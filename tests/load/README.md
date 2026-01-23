# Load Testing Suite

Comprehensive load testing for the Blazing Buffalo self-learning mistake system.

## Quick Start

```bash
# Run all load tests
cd /home/pook/engineer-team
python -m pytest tests/load/test_load.py -v

# Run with asyncio
python tests/load/test_load.py
```

## Test Scenarios

### 1. API Load Tests

**test_load.py** - Programmatic load tests with detailed metrics:

```bash
python tests/load/test_load.py
```

Tests:
- API Health Endpoint (light load: 1,000 req, 50 concurrent)
- API Stats Endpoint (medium load: 5,000 req, 100 concurrent)
- API List Mistakes (heavy load: 10,000 req, 200 concurrent)
- Rate Limiter Enforcement
- Concurrent Playbook Execution (50 concurrent)
- Mistake Detection Pipeline (100+ per minute)
- RCA Pipeline Latency (P95 < 30s target)

### 2. Locust Load Tests

**locustfile.py** - Interactive load testing with web UI:

```bash
# Start with web UI
locust -f tests/load/locustfile.py --host=http://localhost:8000

# Open browser to http://localhost:8089
# Configure users and spawn rate in UI

# Headless mode (for CI/CD)
locust -f tests/load/locustfile.py \
    --host=http://localhost:8000 \
    --users 100 \
    --spawn-rate 10 \
    --run-time 60s \
    --headless
```

User Types:
- **MistakeAPIUser**: Typical CRUD operations (50% read, 5% write)
- **PlaybookAPIUser**: Playbook operations (60% list, 30% get, 10% execute)
- **HealthCheckUser**: Monitoring traffic (constant 1/sec)
- **SpikeTrafficUser**: Burst traffic testing (rate limiting validation)

## Performance Targets

| Metric | Target | Test |
|--------|--------|------|
| API Throughput | > 500 req/s | test_api_list_mistakes |
| API P99 Latency | < 200ms | All API tests |
| Mistake Detection | 100+ /min | test_mistake_detection_throughput |
| RCA P95 Latency | < 30s | test_rca_pipeline_latency |
| Concurrent Playbooks | ≥ 50 | test_concurrent_playbook_execution |
| Error Rate | < 1% | All tests |
| Memory Usage | < 2GB | System monitoring |

## Output Files

```
tests/load/
├── results/
│   └── baseline-YYYYMMDD-HHMMSS.json   # Performance baseline data
│
docs/
└── performance-baseline.md              # Human-readable report
```

## Example Results

```
LOAD TEST SUMMARY
================================================================================

API List Mistakes (Heavy Load)
  Total requests: 10000
  Successful: 9985 (99.9%)
  Failed: 15 (0.1%)
  Duration: 18.45s
  Throughput: 542.1 req/s
  Latency (avg): 92.34ms
  Latency (P50): 85.12ms
  Latency (P95): 145.67ms
  Latency (P99): 189.23ms
```

## Baseline Report

Automatically generated markdown report includes:

- Summary table with pass/fail status
- Detailed results per test
- Latency distribution percentiles
- System recommendations
- Production readiness assessment

## Advanced Usage

### Custom Test Scenarios

```python
from tests.load.test_load import LoadTester

async def custom_test():
    tester = LoadTester()

    # Custom scenario
    result = await tester.test_api_list_mistakes(
        num_requests=20000,
        concurrency=300
    )

    print(f"Throughput: {result.throughput_rps:.1f} req/s")
```

### Locust Custom Scenarios

```python
# Add to locustfile.py

class CustomUser(HttpUser):
    wait_time = between(1, 2)

    @task
    def custom_workflow(self):
        # Your workflow here
        self.client.get("/api/v1/custom")
```

### CI/CD Integration

```bash
# Run load tests in CI
python tests/load/test_load.py > load-test-results.txt

# Check if targets met
python -c "
import json
with open('tests/load/results/baseline-*.json') as f:
    data = json.load(f)
    assert data['api_throughput_rps'] > 500
    assert data['api_p99_latency_ms'] < 200
    assert data['error_rate_pct'] < 1
"
```

## Monitoring During Load Tests

```bash
# Terminal 1: Run load test
python tests/load/test_load.py

# Terminal 2: Monitor system resources
htop

# Terminal 3: Monitor application logs
tail -f logs/api.log

# Terminal 4: Monitor database
watch -n 1 'psql -c "SELECT count(*) FROM pg_stat_activity"'
```

## Troubleshooting

### High Latency

If P99 latency > 200ms:
1. Check database query performance
2. Enable query logging
3. Add database indexes
4. Implement caching layer

### Low Throughput

If throughput < 500 req/s:
1. Check worker processes (uvicorn --workers N)
2. Profile application code
3. Check database connection pool size
4. Review async/await usage

### Rate Limiting Issues

If rate limiter blocks legitimate traffic:
1. Review rate limit configuration
2. Implement token bucket algorithm
3. Add Redis-based distributed rate limiting
4. Consider IP-based vs user-based limits

### Memory Leaks

If memory usage grows over time:
1. Profile with memory_profiler
2. Check for unclosed connections
3. Review cache eviction policies
4. Monitor garbage collection

## Dependencies

```bash
# Install load testing tools
pip install locust pytest pytest-asyncio aiohttp psutil
```

## References

- [Locust Documentation](https://docs.locust.io/)
- [Performance Testing Best Practices](https://developer.mozilla.org/en-US/docs/Web/Performance)
- [FastAPI Performance](https://fastapi.tiangolo.com/deployment/concepts/)
