# Playbook Best Practices

Advanced techniques for creating effective, maintainable playbooks.

## Design Principles

### 1. Single Responsibility

Each playbook should fix **one specific type of mistake**.

**Good:**
```yaml
id: fix-type-error-in-dict-access
name: "Fix TypeError when accessing dict keys"
trigger:
  patterns:
    - "TypeError.*dict.*has no attribute 'get'"
```

**Bad:**
```yaml
id: fix-all-type-errors
name: "Fix any type error"
trigger:
  patterns:
    - "TypeError"  # Too broad
```

### 2. Idempotency

Playbooks should be safe to run multiple times.

**Good:**
```yaml
resolution_steps:
  - id: check_if_fixed
    action: verify
    description: "Check if already fixed"
    exit_if_success: true  # Skip remaining steps

  - id: apply_fix
    action: edit
    description: "Apply fix only if needed"
```

**Bad:**
```yaml
resolution_steps:
  - id: apply_fix
    action: edit
    description: "Always append code"
    # Running twice would append twice
```

### 3. Fail Fast

Detect problems early in the step sequence.

**Good:**
```yaml
resolution_steps:
  - id: validate_context
    action: verify
    description: "Ensure required files exist"
    timeout_tier: instant

  - id: check_permissions
    action: verify
    description: "Ensure write access"
    timeout_tier: instant

  - id: apply_fix  # Only if above succeed
    action: edit
    timeout_tier: fast
```

### 4. Clear Rollback Path

Define how to undo changes if something goes wrong.

```yaml
resolution_steps:
  - id: backup_file
    action: execute
    description: "Create backup before changes"
    command: "cp {{file_path}} {{file_path}}.bak"

  - id: apply_changes
    action: edit
    description: "Modify file"

  - id: verify_success
    action: verify
    description: "Verify changes work"
    on_failure: restore_backup

rollback_steps:
  - id: restore_backup
    action: execute
    description: "Restore from backup"
    command: "mv {{file_path}}.bak {{file_path}}"
```

## Pattern Optimization

### Use Specific Patterns

**Good - Specific:**
```yaml
trigger:
  patterns:
    - "TypeError: expected (dict|Dict\\[.*\\]), got (str|int|list)"
    - "'(str|int|list)' object has no attribute 'get'"
```

**Bad - Too General:**
```yaml
trigger:
  patterns:
    - "Error"
    - "exception"
```

### Anchor Patterns When Possible

```yaml
# Match start and end for precision
trigger:
  patterns:
    - "^TypeError: expected dict, got str$"
    - "^File.*line \\d+.*TypeError"
```

### Use Non-Capturing Groups

For performance:

```yaml
# Good - Non-capturing
patterns:
  - "TypeError: expected (?:dict|list|tuple)"

# Bad - Capturing (slower)
patterns:
  - "TypeError: expected (dict|list|tuple)"
```

## Step Sequencing

### Analyze → Locate → Fix → Verify

Follow this pattern for most playbooks:

```yaml
resolution_steps:
  # 1. ANALYZE - Understand the problem
  - id: read_error_context
    action: read
    description: "Read surrounding code"
    timeout_tier: instant

  # 2. LOCATE - Find affected code
  - id: find_all_occurrences
    action: grep
    description: "Find all similar patterns"
    timeout_tier: fast

  # 3. FIX - Apply changes
  - id: apply_fix
    action: edit
    description: "Fix the issue"
    timeout_tier: fast

  # 4. VERIFY - Confirm success
  - id: run_type_check
    action: verify
    description: "Run type checker"
    timeout_tier: standard
```

### Parallel Steps (When Independent)

```yaml
resolution_steps:
  - id: analyze_imports
    action: grep
    parallel_group: 1  # Can run in parallel
    timeout_tier: fast

  - id: analyze_types
    action: grep
    parallel_group: 1  # Can run in parallel
    timeout_tier: fast

  - id: merge_analysis
    action: execute
    depends_on: [analyze_imports, analyze_types]
    timeout_tier: instant
```

## Timeout Management

### Choose Appropriate Tiers

```yaml
# INSTANT (5s) - File reads, simple checks
- action: read
  timeout_tier: instant

# FAST (30s) - File edits, grep searches
- action: edit
  timeout_tier: fast

# STANDARD (120s) - Test runs, type checks
- action: verify
  timeout_tier: standard

# LONG (600s) - Full builds, deployments
- action: execute
  command: "docker build ."
  timeout_tier: long

# BACKGROUND (async) - Non-blocking operations
- action: execute
  command: "send_notification.sh"
  timeout_tier: background
```

### Escalate Gracefully

```yaml
resolution_steps:
  - id: quick_fix
    action: edit
    timeout_tier: fast
    timeout_seconds: 30
    on_timeout: try_thorough_fix

  - id: try_thorough_fix
    action: execute
    command: "full_analysis.sh"
    timeout_tier: standard
    timeout_seconds: 120
```

## Error Handling

### Graceful Degradation

```yaml
resolution_steps:
  - id: try_automated_fix
    action: edit
    on_failure: manual_fallback

  - id: manual_fallback
    action: execute
    command: "create_ticket.sh '{{error_message}}'"
    description: "Create manual review ticket"
```

### Detailed Error Messages

```yaml
resolution_steps:
  - id: validate_input
    action: verify
    description: "Validate required context fields"
    error_message: "Missing required field: {{missing_field}}. Playbook cannot proceed."

  - id: check_file_exists
    action: verify
    error_message: "File not found: {{file_path}}. Ensure mistake context includes valid file_path."
```

## Success Criteria

### Multi-Level Verification

```yaml
success_criteria:
  # Level 1: Basic checks
  no_new_errors: true
  files_modified: true

  # Level 2: Static analysis
  type_check_passes: true
  lint_passes: true

  # Level 3: Runtime verification
  tests_pass: true

  # Level 4: Integration checks
  custom_checks:
    - name: "API health check"
      command: "curl -f http://localhost:8000/health"
      timeout: 10

    - name: "Database migrations applied"
      command: "python manage.py showmigrations | grep -v '\\[ \\]'"
      timeout: 5
```

### Confidence-Based Criteria

```yaml
success_criteria:
  # High confidence playbooks (>0.9)
  no_new_errors: true
  type_check_passes: true
  tests_pass: true

metadata:
  confidence: 0.95
```

```yaml
success_criteria:
  # Lower confidence playbooks (<0.7)
  no_new_errors: true
  requires_manual_review: true  # Flag for human check

metadata:
  confidence: 0.65
```

## Context Usage

### Required vs Optional Context

```yaml
trigger:
  required_context:
    - file_path
    - line_number
  optional_context:
    - function_name
    - class_name

resolution_steps:
  - id: analyze
    action: read
    file_path: "{{context.file_path}}"  # Required
    line_number: "{{context.line_number | default(0)}}"  # Optional with default
```

### Context Validation

```yaml
resolution_steps:
  - id: validate_context
    action: verify
    description: "Ensure required context present"
    checks:
      - field: file_path
        type: string
        required: true
      - field: line_number
        type: integer
        required: true
        min: 1
```

## Metadata Management

### Track Detailed Metrics

```yaml
metadata:
  # Identification
  id: pb_a21ad52afbd2
  version: "1.2.0"
  created_at: "2026-01-21T10:00:00Z"
  created_by: "rca_001"

  # Performance
  confidence: 0.92
  usage_count: 45
  success_count: 40
  failure_count: 5
  success_rate: 0.89

  # Timing
  last_used: "2026-01-21T11:00:00Z"
  avg_duration_seconds: 45.6
  p95_duration_seconds: 78.2

  # Categorization
  root_cause: "knowledge_gap"
  category: "type_error"
  severity: "medium"
  tags: ["python", "typing", "dict"]

  # Lifecycle
  lifecycle_state: "ACTIVE"
  needs_revalidation: false
```

### Version Playbooks

```yaml
metadata:
  id: type-error-fix
  version: "2.0.0"
  changelog:
    - version: "2.0.0"
      date: "2026-01-21"
      changes: "Added parallel analysis steps"
    - version: "1.1.0"
      date: "2026-01-15"
      changes: "Improved pattern matching"
    - version: "1.0.0"
      date: "2026-01-10"
      changes: "Initial version"
```

## Testing Strategies

### Unit Test Individual Steps

```python
import pytest
from lib.playbook_executor import PlaybookExecutor

@pytest.mark.asyncio
async def test_analyze_step():
    executor = PlaybookExecutor()

    step = {
        "id": "analyze",
        "action": "read",
        "file_path": "test.py",
        "timeout_tier": "instant"
    }

    result = await executor.execute_step(step, context={})

    assert result.success
    assert result.output is not None
```

### Integration Test Full Playbook

```python
@pytest.mark.asyncio
async def test_full_playbook():
    with open('playbooks/type-error-fix.yaml') as f:
        playbook = yaml.safe_load(f)

    executor = PlaybookExecutor()
    result = await executor.execute(
        playbook=playbook,
        context={
            "error_message": "TypeError: expected dict, got str",
            "file_path": "test_module.py"
        },
        dry_run=False
    )

    assert result.success
    assert all(step.success for step in result.steps)
```

### Regression Testing

```bash
# Save test cases
mkdir playbooks/tests
echo "TypeError: expected dict, got str" > playbooks/tests/type_error_1.txt

# Run regression suite
for test in playbooks/tests/*.txt; do
    python3 -m pytest tests/test_playbook_regression.py --test-file=$test
done
```

## Performance Optimization

### Cache Repeated Operations

```yaml
resolution_steps:
  - id: load_file
    action: read
    file_path: "{{context.file_path}}"
    cache_key: "file_{{context.file_path}}"  # Cache result

  - id: analyze_syntax
    action: execute
    command: "ast-parser {{context.file_path}}"
    uses_cache: "file_{{context.file_path}}"  # Reuse cached file
```

### Batch Operations

```yaml
# Bad - Sequential
- id: fix_file_1
  action: edit
- id: fix_file_2
  action: edit
- id: fix_file_3
  action: edit

# Good - Batched
- id: fix_all_files
  action: edit
  files:
    - "{{file_1}}"
    - "{{file_2}}"
    - "{{file_3}}"
```

### Early Exit

```yaml
resolution_steps:
  - id: check_if_already_fixed
    action: verify
    description: "Check if issue already resolved"
    exit_if_success: true  # Skip remaining steps

  - id: expensive_analysis
    action: execute
    # Only runs if above check fails
```

## Security Considerations

### Input Validation

```yaml
resolution_steps:
  - id: validate_file_path
    action: verify
    description: "Ensure file_path is safe"
    checks:
      - "{{context.file_path}} does not contain '..'"
      - "{{context.file_path}} starts with /home/pook/project"
```

### Avoid Command Injection

```yaml
# Bad - Vulnerable to injection
- action: execute
  command: "grep '{{user_input}}' file.txt"

# Good - Use parameterized execution
- action: grep
  pattern: "{{user_input | escape}}"
  file: "file.txt"
```

### Limit Scope

```yaml
# Restrict playbook to specific paths
trigger:
  file_patterns:
    - "src/**/*.py"
    - "!src/tests/**"  # Exclude tests
    - "!src/vendor/**"  # Exclude vendor code
```

## Documentation

### Self-Documenting Playbooks

```yaml
id: fix-type-error-dict-access
name: "Fix TypeError when accessing dict keys"
description: |
  Automatically fixes TypeError that occurs when trying to access
  dictionary keys on non-dict objects (usually strings or None).

  Common scenarios:
  - Function parameter type mismatch
  - API response not properly validated
  - Config loaded as string instead of dict

  Resolution approach:
  1. Identify the variable causing the TypeError
  2. Trace back to where it's assigned
  3. Add type check or fix the assignment
  4. Verify with type checker

  Example fix:
  Before: data.get('key')  # data is str
  After:  data = json.loads(data); data.get('key')

trigger:
  patterns:
    - "TypeError.*dict.*attribute 'get'"

metadata:
  examples:
    - input: "TypeError: 'str' object has no attribute 'get'"
      output: "Added json.loads() before dict access"
  references:
    - "https://docs.python.org/3/library/json.html"
```

### Inline Step Documentation

```yaml
resolution_steps:
  - id: locate_error_line
    action: grep
    description: "Find the line causing TypeError"
    timeout_tier: fast
    notes: |
      Uses stack trace to locate exact line.
      Falls back to pattern search if stack trace unavailable.
```

## Monitoring & Alerts

### Track Key Metrics

```yaml
metadata:
  monitoring:
    alert_on_failure_rate: 0.3  # Alert if >30% failures
    alert_on_duration: 120      # Alert if >120s avg duration
    alert_on_circuit_open: true # Alert when circuit opens

    dashboards:
      - "grafana://playbook-health"
      - "datadog://playbook-metrics"
```

### Log Structured Data

```python
import logging
import structlog

logger = structlog.get_logger()

logger.info(
    "playbook_executed",
    playbook_id="pb_a21ad52afbd2",
    success=True,
    duration_seconds=45.6,
    steps_executed=4,
    confidence=0.92
)
```

## Collaboration

### Code Review Playbooks

```yaml
metadata:
  reviewers:
    - "alice@example.com"
    - "bob@example.com"
  last_reviewed: "2026-01-15T10:00:00Z"
  review_notes: "Approved with suggestions for timeout optimization"
```

### Share Common Patterns

```yaml
# Base playbook: playbooks/base/python-error-fix.yaml
id: python-error-fix-base
description: "Base template for Python error fixes"

resolution_steps:
  - id: read_code
    action: read
    timeout_tier: instant
  - id: analyze_error
    action: execute
    command: "python-error-analyzer {{file_path}}"
  - id: verify_fix
    action: verify
    timeout_tier: standard

# Specific playbook: playbooks/python/type-error-fix.yaml
id: type-error-fix
extends: python-error-fix-base
# Inherit base steps, add specific trigger
trigger:
  patterns:
    - "TypeError"
```

## Common Anti-Patterns

### ❌ Don't Ignore Errors

```yaml
# Bad
resolution_steps:
  - action: execute
    command: "risky_command || true"  # Silently ignore failures
```

### ❌ Don't Use Unbounded Operations

```yaml
# Bad - Could run forever
- action: execute
  command: "while true; do check_status; done"
  timeout_tier: background
```

### ❌ Don't Hardcode Paths

```yaml
# Bad
- action: edit
  file_path: "/home/alice/project/main.py"  # Won't work for other users

# Good
- action: edit
  file_path: "{{project_root}}/main.py"
```

### ❌ Don't Overfit to Single Case

```yaml
# Bad - Too specific
trigger:
  patterns:
    - "TypeError: 'str' object has no attribute 'get' at line 42 in main.py"

# Good - General pattern
trigger:
  patterns:
    - "TypeError.*'str'.*has no attribute 'get'"
```

## Checklist

Before deploying a playbook:

- [ ] Trigger patterns are specific enough (low false positive rate)
- [ ] Resolution steps follow Analyze → Locate → Fix → Verify pattern
- [ ] Timeout tiers are appropriate for each step
- [ ] Success criteria are well-defined and verifiable
- [ ] Playbook is idempotent (safe to run multiple times)
- [ ] Error handling includes rollback or fallback
- [ ] Context validation is performed early
- [ ] Documentation is clear and includes examples
- [ ] Tested in dry-run mode
- [ ] Reviewed by at least one other person

## Next Steps

- **[Lifecycle Management](lifecycle.md)** - Understand aging and archival
- **[Troubleshooting](../troubleshooting.md)** - Debug playbook issues
- **[API Reference](../api-reference.md)** - Trigger playbooks programmatically
