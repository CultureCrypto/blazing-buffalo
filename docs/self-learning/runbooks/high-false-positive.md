# Runbook: High False Positive Rate

**Alert**: Playbook triggering on wrong mistakes

**Severity**: Medium

**Impact**: Wasted execution time, potential incorrect fixes

## Symptoms

- Alert: `playbook_false_positive_rate{playbook_id="pb_*"} > 0.3`
- Many playbook executions fail success criteria
- Manual review shows playbook triggered incorrectly
- User complaints about irrelevant fixes

## Immediate Actions

### 1. Assess Scope (3 minutes)

```bash
# Check false positive rate
curl "http://localhost:8200/playbooks/{playbook_id}/metrics" | jq '.false_positive_rate'

# Get recent executions
curl "http://localhost:8200/playbooks/{playbook_id}/executions?limit=20"

# Count false positives vs true positives
curl "http://localhost:8200/playbooks/{playbook_id}/executions?status=failed" | jq '.total'
curl "http://localhost:8200/playbooks/{playbook_id}/executions?status=success" | jq '.total'
```

**Decision Point:**
- False positive rate >50% → **Disable playbook immediately**
- False positive rate 30-50% → **Proceed with investigation**
- False positive rate <30% → **Monitor, investigate later**

### 2. Disable if Critical (1 minute)

```bash
# Temporarily disable high false positive playbook
curl -X PATCH http://localhost:8200/playbooks/{playbook_id} \
  -H "Content-Type: application/json" \
  -d '{"enabled": false, "reason": "High false positive rate"}'

# Or increase confidence threshold to effectively disable
curl -X PATCH http://localhost:8200/playbooks/{playbook_id} \
  -H "Content-Type: application/json" \
  -d '{"metadata": {"confidence": 0.3}}'  # Below 0.7 threshold
```

## Investigation

### Analyze Trigger Patterns

#### Step 1: Review Trigger Configuration

```bash
# Get playbook configuration
curl http://localhost:8200/playbooks/{playbook_id} | jq '.trigger'
```

```yaml
# Example output
trigger:
  patterns:
    - "TypeError"  # TOO BROAD!
  detection_methods:
    - "runtime_error"
  file_patterns:
    - "*.py"
```

**Common Issues:**
- **Too broad patterns**: "Error", "exception", "failed"
- **Missing anchors**: No start/end anchors
- **No file filtering**: Matches all files
- **No exclusions**: Includes tests, vendor code

#### Step 2: Analyze False Positive Cases

```bash
# Get failed executions
curl "http://localhost:8200/playbooks/{playbook_id}/executions?status=failed&limit=10"

# For each, check the mistake that triggered it
for exec_id in $(curl ... | jq -r '.executions[].id'); do
  curl "http://localhost:8200/playbooks/executions/$exec_id" | jq '{mistake_id, error_message, why_failed}'
done
```

**Look for patterns:**
```bash
# Common false positives
- "TypeError" but different context than intended
- "AttributeError" confused with "TypeError"
- Test files when playbook meant for production code
```

## Resolution

### Option 1: Tighten Trigger Patterns

**Before (too broad):**
```yaml
trigger:
  patterns:
    - "TypeError"
```

**After (specific):**
```yaml
trigger:
  patterns:
    - "TypeError: expected (dict|Dict\\[.*\\]), got (str|int|list)"
    - "'(str|int|list)' object has no attribute 'get'"
```

**Test regex before deploying:**
```python
import re

pattern = r"TypeError: expected (dict|Dict\[.*\]), got (str|int|list)"

# True positive
test1 = "TypeError: expected dict, got str"
assert re.search(pattern, test1)

# False positive (should NOT match)
test2 = "TypeError: unsupported operand type"
assert not re.search(pattern, test2)
```

### Option 2: Add File Filtering

```yaml
trigger:
  patterns:
    - "TypeError"
  file_patterns:
    - "src/api/**/*.py"      # Only API code
    - "!src/api/tests/**"    # Exclude tests
    - "!**/vendor/**"        # Exclude vendor
    - "!**/.venv/**"         # Exclude virtualenv
```

### Option 3: Add Detection Method Filtering

```yaml
trigger:
  patterns:
    - "TypeError"
  detection_methods:
    - "runtime_error"        # Only runtime errors
  # Exclude:
  # - "test_failure"        # Not test failures
  # - "tool_failure"        # Not tool failures
```

### Option 4: Add Context Validation

```yaml
resolution_steps:
  - id: validate_applies
    action: verify
    description: "Check this playbook actually applies"
    checks:
      - "error_message contains 'expected dict'"
      - "file_path matches '^src/api/'"
      - "function_name not in ['test_', 'mock_']"
    on_failure: skip_playbook
    timeout_tier: instant

  - id: actual_fix
    action: edit
    # Only runs if validation passes
```

### Option 5: Increase Confidence Threshold

```yaml
metadata:
  confidence: 0.95  # Increase from 0.7

  # With threshold at 0.7, playbook won't execute if confidence <0.7
  # Higher confidence = more certain it's the right fix
```

## Validation

### Test Pattern Changes

```python
import re
import yaml

# Load updated playbook
with open('playbooks/pb_updated.yaml') as f:
    playbook = yaml.safe_load(f)

# Test cases
test_cases = [
    # True positives (should match)
    ("TypeError: expected dict, got str", True),
    ("'str' object has no attribute 'get'", True),

    # False positives (should NOT match)
    ("TypeError: unsupported operand type", False),
    ("AttributeError: 'NoneType' object", False),
    ("SyntaxError: invalid syntax", False),
]

# Test each pattern
for pattern_str in playbook['trigger']['patterns']:
    pattern = re.compile(pattern_str, re.IGNORECASE)

    for test_msg, should_match in test_cases:
        matches = bool(pattern.search(test_msg))

        if matches != should_match:
            print(f"FAIL: Pattern '{pattern_str}'")
            print(f"  Message: {test_msg}")
            print(f"  Expected: {should_match}, Got: {matches}")
        else:
            print(f"PASS: {test_msg}")
```

### A/B Test

```bash
# Create test version
cp playbooks/pb_original.yaml playbooks/pb_test.yaml

# Edit pb_test.yaml with new patterns

# Run both on same mistakes
for mistake_id in $(recent_mistake_ids); do
  # Original
  original_result=$(test_playbook_trigger playbooks/pb_original.yaml $mistake_id)

  # New version
  test_result=$(test_playbook_trigger playbooks/pb_test.yaml $mistake_id)

  echo "$mistake_id: original=$original_result, test=$test_result"
done
```

### Monitor After Deployment

```bash
# Deploy updated playbook
cp playbooks/pb_updated.yaml playbooks/pb_a21ad52afbd2.yaml

# Reset circuit breaker
curl -X POST http://localhost:8200/playbooks/pb_a21ad52afbd2/circuit-breaker/reset \
  -d '{"reason": "Fixed false positive pattern", "confirmed": true}'

# Re-enable
curl -X PATCH http://localhost:8200/playbooks/pb_a21ad52afbd2 \
  -d '{"enabled": true}'

# Monitor for 1 hour
watch -n 60 'curl -s http://localhost:8200/playbooks/pb_a21ad52afbd2/metrics | jq "{success_rate, false_positive_rate}"'
```

## Prevention

### Pattern Development Checklist

Before deploying trigger patterns:

- [ ] Tested against 10+ true positive examples
- [ ] Tested against 10+ false positive examples
- [ ] Anchored where appropriate (`^`, `$`, `\b`)
- [ ] Uses non-capturing groups for performance
- [ ] File patterns exclude tests/vendor
- [ ] Context validation in first step
- [ ] Confidence threshold appropriate (0.8+ for auto-execution)

### Create Test Suite

```bash
# Create test cases directory
mkdir -p playbooks/tests/pb_a21ad52afbd2/

# Add positive examples
cat > playbooks/tests/pb_a21ad52afbd2/positive_001.txt << EOF
TypeError: expected dict, got str
File: src/api/handler.py
Context: def process(data: dict):
EOF

# Add negative examples
cat > playbooks/tests/pb_a21ad52afbd2/negative_001.txt << EOF
TypeError: unsupported operand type
File: src/math/calc.py
Context: result = x + y
EOF

# Run tests
python3 scripts/test_playbook_triggers.py playbooks/pb_a21ad52afbd2.yaml
```

### Monitoring Dashboard

**Grafana Panel:**
```yaml
- title: "Playbook False Positive Rate"
  targets:
    - expr: |
        (
          sum(playbook_executions_failed_total{reason="success_criteria_not_met"}) by (playbook_id)
          /
          sum(playbook_executions_total) by (playbook_id)
        )
  alert:
    conditions:
      - value > 0.3
    for: 30m
```

## Post-Resolution

### Document Pattern

Add to playbook documentation:

```yaml
metadata:
  pattern_notes: |
    Trigger pattern specifically matches TypeError when:
    - Expected type is dict/Dict
    - Actual type is str/int/list
    - Occurs during attribute access (.get())

    Does NOT match:
    - Other TypeError variants
    - Test files
    - Vendor code
```

### Update Knowledge Base

```bash
# Add to knowledge graph
kg-update-light.sh playbook_pattern_fix "Fixed false positive in pb_a21ad52afbd2 by tightening regex" \
  --tags "playbook,pattern,false-positive"
```

### Share Learning

Create PR to update playbook best practices:

```markdown
## Common False Positive Patterns to Avoid

1. **Too Broad:** `"TypeError"` → Use: `"TypeError: expected dict, got (str|int)"`
2. **No File Filtering:** `"*.py"` → Use: `"src/**/*.py", "!tests/**"`
3. **Missing Context:** Just pattern → Use: Pattern + context validation
```

## Related Runbooks

- [Circuit Breaker Open](circuit-breaker-open.md)
- [Backup Failed](backup-failed.md)
