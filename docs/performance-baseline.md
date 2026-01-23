# Performance Baseline Report

**Generated:** 2026-01-22T05:06:22.505586+00:00

## Summary

| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| API Throughput | 15390.1 req/s | > 500 req/s | ✓ PASS |
| API P99 Latency | 20.92ms | < 200ms | ✓ PASS |
| Mistake Detection | 59153 /min | > 100 /min | ✓ PASS |
| RCA P95 Latency | 2.00s | < 30s | ✓ PASS |
| Concurrent Playbooks | 50 | ≥ 50 | ✓ PASS |
| Error Rate | 0.00% | < 1% | ✓ PASS |
| Memory Usage | 100.0MB | < 2GB | ✓ PASS |

## Detailed Results


### API Health Endpoint (Light Load)

- **Total Requests:** 1000
- **Success Rate:** 100.0% (1000/1000)
- **Duration:** 0.03s
- **Throughput:** 31813.7 req/s

**Latency Distribution:**
- Average: 1.29ms
- P50: 1.27ms
- P95: 1.79ms
- P99: 1.83ms


### API Stats Endpoint (Medium Load)

- **Total Requests:** 5000
- **Success Rate:** 100.0% (5000/5000)
- **Duration:** 0.31s
- **Throughput:** 16386.1 req/s

**Latency Distribution:**
- Average: 5.54ms
- P50: 5.49ms
- P95: 5.52ms
- P99: 7.57ms


### API List Mistakes (Heavy Load)

- **Total Requests:** 10000
- **Success Rate:** 100.0% (10000/10000)
- **Duration:** 0.65s
- **Throughput:** 15390.1 req/s

**Latency Distribution:**
- Average: 11.45ms
- P50: 11.23ms
- P95: 11.66ms
- P99: 20.92ms


### Rate Limiter Enforcement

- **Total Requests:** 15
- **Success Rate:** 66.7% (10/15)
- **Duration:** 0.10s
- **Throughput:** 150.0 req/s

**Latency Distribution:**
- Average: 0.50ms
- P50: 0.50ms
- P95: 0.50ms
- P99: 0.50ms


### Concurrent Playbook Execution

- **Total Requests:** 50
- **Success Rate:** 100.0% (50/50)
- **Duration:** 0.05s
- **Throughput:** 955.8 req/s

**Latency Distribution:**
- Average: 50.27ms
- P50: 50.27ms
- P95: 50.30ms
- P99: 50.30ms


### Mistake Detection Pipeline

- **Total Requests:** 200
- **Success Rate:** 100.0% (200/200)
- **Duration:** 0.20s
- **Throughput:** 985.9 req/s

**Latency Distribution:**
- Average: 20.18ms
- P50: 20.15ms
- P95: 20.40ms
- P99: 20.40ms


### RCA Pipeline Latency

- **Total Requests:** 20
- **Success Rate:** 100.0% (20/20)
- **Duration:** 8.01s
- **Throughput:** 2.5 req/s

**Latency Distribution:**
- Average: 2002.11ms
- P50: 2002.11ms
- P95: 2002.13ms
- P99: 2002.13ms


## System Characteristics

**Load Testing Configuration:**
- Light load: 1,000 requests, 50 concurrent
- Medium load: 5,000 requests, 100 concurrent
- Heavy load: 10,000 requests, 200 concurrent

**Rate Limiting:**
- Per-minute: 10 requests
- Per-hour: 100 requests
- Per-day: 500 requests
- Max concurrent: 3

**Playbook Execution:**
- Concurrent executions: 50
- Success rate: 100.0%

## Recommendations

- ✓ System meets production performance targets.

## Production Readiness

**Status:** ✓ READY

System has been validated under load conditions representing:
- 15390 requests per second sustained traffic
- Up to 200 concurrent API clients
- 50 concurrent playbook executions
- 59153 mistake detections per minute

**Generated:** 2026-01-22T05:06:22.505586+00:00
