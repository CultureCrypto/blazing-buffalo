# Runbook: Circuit Breaker Open

**Alert**: Circuit breaker opened for playbook

**Severity**: Medium

**Impact**: Playbook auto-execution disabled until resolved

## Symptoms

- Alert: `circuit_breaker_open{playbook_id="pb_*"} == 1`
- API returns: `CIRCUIT_OPEN` error
- Playbook no longer auto-executing
- Dashboard shows circuit breaker status: OPEN

## Immediate Actions

### 1. Assess Impact (2 minutes)

```bash
# Check which playbook is affected
curl http://localhost:8200/playbooks/circuit-breaker-status | jq '.open_circuits'

# Check recent failures
curl "http://localhost:8200/playbooks/{playbook_id}/executions?status=failed&limit=10"

# Estimate affected mistakes
curl "http://localhost:8200/mistakes?playbook_id={playbook_id}&since=1h"
```

**Decision Point:**
- If critical playbook (>50 uses/day) → **Escalate immediately**
- If non-critical → **Proceed with investigation**

### 2. Identify Failure Pattern (5 minutes)

```bash
# Get circuit breaker details
curl http://localhost:8200/playbooks/{playbook_id}/circuit-breaker

# Example output:
# {
#   "state": "OPEN",
#   "consecutive_failures": 5,
#   "last_failure": "2026-01-21T10:00:00Z",
#   "failure_reasons": [
#     "Step 'analyze' timed out after 30s",
#     "Step 'fix_type' failed: File not found",
#     "Step 'analyze' timed out after 30s",
#     ...
#   ]
# }
```

**Check logs:**
```bash
# Last 20 failures
grep "playbook_id={playbook_id}" /var/log/blazing_buffalo.log | grep "FAILED" | tail -20

# Or via API
curl "http://localhost:8200/playbooks/{playbook_id}/logs?level=ERROR&limit=20"
```

**Common Patterns:**
- All failures: **Same step** → Step issue
- All failures: **Timeout** → Performance issue
- Random steps: **Different errors** → Context/data issue

## Investigation

### Case 1: Timeout Issues

**Symptoms:** All failures show "timed out after Xs"

**Steps:**

1. **Check step timeout configuration:**
```yaml
# In playbook YAML
resolution_steps:
  - id: slow_step
    timeout_tier: fast    # 30s
    timeout_seconds: 30
```

2. **Analyze step performance:**
```bash
# Get average duration for this step
curl "http://localhost:8200/playbooks/{playbook_id}/step-metrics?step_id=slow_step"

# Example output:
# {
#   "avg_duration": 45.2,
#   "p95_duration": 78.3,
#   "timeout": 30,
#   "timeout_rate": 0.65
# }
```

3. **Solution options:**

**Option A: Increase timeout (quick fix)**
```yaml
# Edit playbook
resolution_steps:
  - id: slow_step
    timeout_tier: standard  # Change to 120s
    timeout_seconds: 120
```

**Option B: Optimize step**
```yaml
# Before - Broad search
- id: find_pattern
  action: grep
  pattern: "error"
  path: "."  # Entire codebase

# After - Targeted search
- id: find_pattern
  action: grep
  pattern: "error"
  path: "src/api"  # Specific directory
```

### Case 2: File Not Found Errors

**Symptoms:** Failures show "File not found" or "Path does not exist"

**Steps:**

1. **Check context:**
```bash
# Get failed execution details
curl "http://localhost:8200/playbooks/executions/{execution_id}"

# Check context provided
{
  "context": {
    "file_path": "module.py",  # Relative path?
    "error_message": "..."
  }
}
```

2. **Solution:**

**Add path resolution step:**
```yaml
resolution_steps:
  - id: resolve_path
    action: execute
    description: "Resolve relative path to absolute"
    command: "realpath {{context.file_path}}"
    save_output_as: "absolute_path"

  - id: read_file
    action: read
    file_path: "{{absolute_path}}"  # Use resolved path
```

**Or add validation:**
```yaml
resolution_steps:
  - id: validate_file_exists
    action: verify
    description: "Check file exists before proceeding"
    command: "test -f {{context.file_path}}"
    on_failure: skip_playbook
```

### Case 3: Permission Errors

**Symptoms:** Failures show "Permission denied"

**Steps:**

1. **Check file permissions:**
```bash
# Find the file causing issues
grep "Permission denied" /var/log/blazing_buffalo.log | tail -1

# Check permissions
ls -l /path/to/problematic/file
```

2. **Solution:**

**Temporary: Grant permissions**
```bash
chmod 644 /path/to/file
```

**Permanent: Fix playbook scope**
```yaml
# Limit to files we have permission to modify
trigger:
  file_patterns:
    - "src/**/*.py"  # Only src directory
    - "!vendor/**"   # Exclude vendor
    - "!.venv/**"    # Exclude venv
```

### Case 4: Context Missing Fields

**Symptoms:** Failures show "KeyError: 'field_name'" or "Missing required context"

**Steps:**

1. **Check required context:**
```yaml
# In playbook
trigger:
  required_context:
    - file_path
    - line_number
    - error_message
```

2. **Solution:**

**Add context validation:**
```yaml
resolution_steps:
  - id: validate_context
    action: verify
    description: "Validate required context fields"
    required_fields:
      - file_path
      - line_number
    on_failure: skip_playbook
```

**Or use defaults:**
```yaml
resolution_steps:
  - id: use_file
    action: read
    file_path: "{{context.file_path | default('src/main.py')}}"
```

## Resolution

### Reset Circuit Breaker

**Only after fixing underlying issue!**

```bash
# Reset circuit breaker
curl -X POST http://localhost:8200/playbooks/{playbook_id}/circuit-breaker/reset \
  -H "Content-Type: application/json" \
  -d '{
    "reason": "Fixed timeout issue - increased from 30s to 120s",
    "confirmed": true
  }'

# Verify reset
curl http://localhost:8200/playbooks/{playbook_id}/circuit-breaker
# Should show: "state": "CLOSED"
```

### Test Playbook

```bash
# Execute manually in dry-run mode
curl -X POST http://localhost:8200/playbooks/execute \
  -H "Content-Type: application/json" \
  -d '{
    "playbook_id": "{playbook_id}",
    "context": {
      "error_message": "test error",
      "file_path": "test.py"
    },
    "dry_run": true
  }'

# Monitor execution
curl http://localhost:8200/playbooks/executions/{execution_id}

# If successful, run for real
curl -X POST http://localhost:8200/playbooks/execute \
  -H "Content-Type: application/json" \
  -d '{
    "playbook_id": "{playbook_id}",
    "context": {...},
    "dry_run": false
  }'
```

## Prevention

### Adjust Circuit Breaker Threshold

If too sensitive:

```bash
# Increase threshold (.env)
CIRCUIT_BREAKER_THRESHOLD=10  # Instead of 5
CIRCUIT_BREAKER_TIMEOUT=600   # 10 minutes instead of 5
```

### Add Monitoring

**Grafana Alert:**
```yaml
alert: PlaybookCircuitBreakerOpen
expr: circuit_breaker_open{playbook_id=~".*"} == 1
for: 5m
labels:
  severity: warning
annotations:
  summary: "Circuit breaker open for playbook {{ $labels.playbook_id }}"
```

### Improve Playbook Robustness

1. **Add validation steps**
2. **Use appropriate timeouts**
3. **Handle edge cases**
4. **Test with varied contexts**

## Escalation

**Escalate if:**
- Cannot identify root cause within 15 minutes
- Critical playbook (>100 uses/day)
- Multiple circuit breakers open simultaneously
- Pattern suggests systemic issue

**Escalation Path:**
1. Senior Engineer
2. On-Call SRE
3. System Architect

## Post-Incident

### Update Runbook

Document new failure patterns discovered.

### Review Playbook

```bash
# Check success rate history
curl "http://localhost:8200/playbooks/{playbook_id}/metrics?period=30d"

# Consider:
# - If success rate <70% → Redesign playbook
# - If timeout rate >30% → Optimize or increase timeouts
# - If error rate >20% → Add better validation
```

### Update Documentation

Add case to [Troubleshooting](../troubleshooting.md#circuit-breaker-open).

## Related Runbooks

- [High False Positive Rate](high-false-positive.md)
- [Backup Failed](backup-failed.md)
