# Runbook: RCA Rate Limit

**Alert**: `RCARateLimitExceeded`
**Severity**: Info
**Component**: RCA Pipeline

## Symptoms

Rate limiting is active for RCA requests to external APIs.

## Impact

- Some RCA requests are queued or delayed
- Not a failure - this is expected protective behavior
- Prevents overwhelming external APIs
- May indicate capacity planning needed if sustained

## Investigation

```bash
# Check rate limit metrics
curl "http://localhost:8000/metrics" | grep "rate_limit"

# View request queue
curl "http://localhost:8000/api/rca/queue-status"
```

## Resolution

### If Transient

No action needed - rate limiting will resolve naturally as request rate decreases.

### If Sustained

Consider:
- Increasing rate limits (if APIs allow)
- Adding additional API keys
- Implementing request batching
- Caching RCA results for similar mistakes

## Prevention

Monitor RCA request patterns and plan capacity accordingly.
