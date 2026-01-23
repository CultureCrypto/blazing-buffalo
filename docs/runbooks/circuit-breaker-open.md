# Runbook: Circuit Breaker Open

**Alert**: `PlaybookCircuitBreakerOpen`
**Severity**: Warning
**Component**: Playbook Executor

## Symptoms

Circuit breaker has been open for 5+ minutes for a specific playbook, indicating repeated execution failures.

## Impact

- Automated remediation disabled for affected mistake pattern
- Users must manually resolve mistakes that would normally be auto-fixed
- Reduced system effectiveness

## Investigation

### 1. Check playbook execution logs

```bash
# View recent executions for the playbook
curl "http://localhost:8000/api/playbooks/{playbook_id}/executions?limit=20"

# Check error patterns
grep "playbook_id={playbook_id}" /var/log/blazing-buffalo/playbook-executor.log | tail -50
```

### 2. Review circuit breaker metrics

```bash
# Check circuit breaker state
curl "http://localhost:8000/metrics" | grep "blazing_buffalo_circuit_breaker_state{playbook_id=\"{playbook_id}\"}"

# Check failure counts
curl "http://localhost:8000/metrics" | grep "blazing_buffalo_circuit_breaker_failures{playbook_id=\"{playbook_id}\"}"
```

### 3. Analyze failure reasons

Common causes:
- Playbook code has bugs
- External dependencies unavailable
- Environment changes (API changes, tool updates)
- Insufficient permissions
- Invalid assumptions about mistake context

## Resolution

### Quick Fix (Temporary)

If failures are due to transient issues:

```bash
# Manually reset circuit breaker
curl -X POST "http://localhost:8000/api/playbooks/{playbook_id}/circuit-breaker/reset"
```

### Permanent Fix

1. **Fix the playbook**:
   ```bash
   # Edit playbook
   vim /home/pook/engineer-team/playbooks/{playbook_id}.py

   # Test manually
   python -m playbooks.{playbook_id} --test
   ```

2. **Update playbook version**:
   ```bash
   # Increment version in playbook metadata
   # Deploy updated playbook
   ```

3. **Deprecate if unfixable**:
   ```bash
   # Mark playbook as deprecated
   curl -X POST "http://localhost:8000/api/playbooks/{playbook_id}/deprecate" \
     -H "Content-Type: application/json" \
     -d '{"reason": "No longer applicable", "replacement": null}'
   ```

## Prevention

- Add comprehensive error handling to playbooks
- Include pre-execution validation checks
- Test playbooks against diverse mistake scenarios
- Monitor playbook success rates proactively
- Set up CI/CD tests for playbooks before deployment

## Escalation

If unable to resolve within 30 minutes:
- Notify: @engineering-oncall
- Channel: #blazing-buffalo-incidents
- Include: playbook_id, error patterns, investigation results
