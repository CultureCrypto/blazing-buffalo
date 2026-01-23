# Runbook: RCA Latency High

**Alert**: `RCALatencyHigh`
**Severity**: Warning
**Component**: RCA Pipeline

## Symptoms

95th percentile RCA (Root Cause Analysis) latency exceeds 30 seconds for 10+ minutes.

## Impact

- Delayed feedback to users
- Slower mistake resolution
- Degraded user experience
- Potential timeout errors in UI

## Investigation

### 1. Check RCA pipeline metrics

```bash
# View latency percentiles
curl "http://localhost:8000/metrics" | grep "blazing_buffalo_rca_latency"

# Check queue depth
curl "http://localhost:8000/api/rca/stats"
```

### 2. Identify bottlenecks

```bash
# Check external API latencies
curl "http://localhost:8000/metrics" | grep "external_api_latency"

# View RCA pipeline stages
psql -d blazing_buffalo -c "
  SELECT
    stage,
    AVG(duration_ms) as avg_ms,
    MAX(duration_ms) as max_ms,
    COUNT(*) as executions
  FROM rca_stage_timings
  WHERE created_at > NOW() - INTERVAL '15 minutes'
  GROUP BY stage
  ORDER BY avg_ms DESC;
"
```

### 3. Check system resources

```bash
# CPU usage
top -b -n 1 | grep "python.*rca"

# Memory usage
ps aux | grep "rca" | awk '{print $4, $11}'

# Database connections
psql -d blazing_buffalo -c "
  SELECT count(*) FROM pg_stat_activity
  WHERE application_name LIKE '%rca%';
"
```

## Resolution

### Quick Fixes

1. **Increase RCA worker pool**:
   ```bash
   # Edit configuration
   vim /home/pook/engineer-team/config/rca_pipeline.yaml
   # Set: worker_pool_size: 10  # Increase from 5

   # Restart RCA service
   systemctl restart blazing-buffalo-rca
   ```

2. **Enable caching for repeated analyses**:
   ```bash
   curl -X POST "http://localhost:8000/api/rca/config" \
     -H "Content-Type: application/json" \
     -d '{"cache_enabled": true, "cache_ttl": 3600}'
   ```

3. **Reduce analysis depth temporarily**:
   ```bash
   curl -X POST "http://localhost:8000/api/rca/config" \
     -H "Content-Type: application/json" \
     -d '{"max_depth": 3, "max_similar_cases": 5}'
   ```

### Performance Optimizations

1. **Optimize database queries**:
   ```sql
   -- Add indexes for common RCA queries
   CREATE INDEX CONCURRENTLY idx_mistakes_category_created
   ON mistakes(category, created_at DESC);

   CREATE INDEX CONCURRENTLY idx_playbook_executions_outcome
   ON playbook_executions(mistake_id, outcome, created_at);
   ```

2. **Implement request batching**:
   ```python
   # In lib/mistake_rca.py
   # Enable batch processing for similar mistakes
   RCA_BATCH_SIMILAR = True
   RCA_BATCH_WINDOW_MS = 500
   ```

3. **Tune external API timeouts**:
   ```bash
   # Reduce timeout for non-critical API calls
   vim /home/pook/engineer-team/config/external_apis.yaml
   # Set: timeout_ms: 5000  # Reduce from 10000
   ```

### Long-term Solutions

1. **Implement async RCA processing**:
   - Return immediate acknowledgment to user
   - Process RCA in background
   - Notify user when complete

2. **Add RCA result caching layer** (Redis):
   ```bash
   # Cache RCA results by mistake fingerprint
   redis-cli SET "rca:{mistake_fingerprint}" "{rca_result}" EX 3600
   ```

3. **Profile and optimize slow stages**:
   ```bash
   # Profile RCA pipeline
   python -m cProfile -o rca_profile.stats scripts/run_rca.py
   python -m pstats rca_profile.stats
   ```

## Prevention

- Monitor RCA latency continuously
- Set up capacity alerts before degradation
- Load test RCA pipeline regularly
- Implement circuit breakers for external APIs
- Cache frequently accessed data
- Regular performance profiling

## Escalation

If latency exceeds 60s (critical threshold):
- Notify: @backend-team, @platform-oncall
- Channel: #blazing-buffalo-performance
- Include: bottleneck analysis, resource metrics, attempted optimizations
