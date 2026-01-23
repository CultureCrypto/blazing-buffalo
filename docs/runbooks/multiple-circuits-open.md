# Runbook: Multiple Circuit Breakers Open

**Alert**: `MultipleCircuitBreakersOpen`
**Severity**: Critical
**Component**: Playbook Executor

## Symptoms

3+ playbook circuit breakers are open simultaneously, indicating systemic issues.

## Impact

- **CRITICAL**: Automated remediation significantly degraded
- Multiple mistake patterns cannot be auto-fixed
- Platform-wide problem affecting playbook execution
- User experience severely impacted

## Investigation

### 1. Identify affected playbooks

```bash
# List all open circuit breakers
curl "http://localhost:8000/metrics" | grep "blazing_buffalo_circuit_breaker_state{.*}=1"

# Get playbook details
curl "http://localhost:8000/api/playbooks?status=circuit_open"
```

### 2. Check for common root cause

```bash
# Check if errors are similar across playbooks
for playbook_id in $(curl -s "http://localhost:8000/api/playbooks?status=circuit_open" | jq -r '.[].id'); do
  echo "=== $playbook_id ==="
  tail -5 /var/log/blazing-buffalo/playbooks/${playbook_id}.log
done
```

### 3. Check platform health

Common systemic causes:
- Database connectivity issues
- External API outages
- File system problems
- Permission changes
- Resource exhaustion
- Recent platform updates

```bash
# Check database
psql -d blazing_buffalo -c "SELECT 1;"

# Check disk space
df -h

# Check memory
free -h

# Recent deployments
git log --since="24 hours ago" --oneline
```

## Resolution

### Immediate Actions

1. **Check recent changes**:
   ```bash
   # Rollback if recent deployment correlates
   git revert HEAD
   systemctl restart blazing-buffalo-api
   ```

2. **Fix infrastructure issues**:
   - Restore database connectivity
   - Fix file permissions
   - Clear disk space
   - Restart failed services

3. **Temporarily disable affected playbooks** (if unfixable):
   ```bash
   curl -X POST "http://localhost:8000/api/playbooks/bulk-disable" \
     -H "Content-Type: application/json" \
     -d '{"playbook_ids": ["id1", "id2", "id3"], "reason": "systemic-failure"}'
   ```

## Escalation

**ESCALATE IMMEDIATELY - This is a critical systemic issue**

- Notify: @platform-team, @engineering-lead
- Channel: #incidents
- Page: On-call engineer
- Include: affected playbooks, common errors, investigation timeline
