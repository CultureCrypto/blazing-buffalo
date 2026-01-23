# Creating Playbooks

Learn how to create effective playbooks for automatic mistake resolution.

## Playbook Structure

A playbook is a YAML file that defines:
- **Trigger patterns** - When to execute
- **Resolution steps** - What actions to take
- **Success criteria** - How to verify success
- **Metadata** - Confidence, lifecycle, usage tracking

## Basic Playbook

```yaml
id: type-error-fix
name: "Fix TypeError in function calls"

trigger:
  patterns:
    - "TypeError"
    - "expected.*got"
  detection_methods:
    - "runtime_error"
    - "tool_failure"
  file_patterns:
    - "*.py"

resolution_steps:
  - id: analyze_type
    action: read
    description: "Read function signature"
    timeout_tier: instant
    timeout_seconds: 5

  - id: find_calls
    action: grep
    description: "Find all call sites"
    timeout_tier: fast
    timeout_seconds: 30

  - id: fix_type
    action: edit
    description: "Fix type mismatch"
    timeout_tier: fast
    timeout_seconds: 30

  - id: verify
    action: verify
    description: "Run type checker"
    timeout_tier: fast
    timeout_seconds: 30

success_criteria:
  no_new_errors: true
  type_check_passes: true

metadata:
  confidence: 0.95
  root_cause: "knowledge_gap"
  created_at: "2026-01-21T10:00:00Z"
  usage_count: 0
  success_rate: 0.0
  last_used: null
```

## Trigger Configuration

### Patterns

Regular expressions matching error messages:

```yaml
trigger:
  patterns:
    - "TypeError"                    # Simple string match
    - "expected.*got"                # Regex pattern
    - "cannot.*type.*'(str|int)'"    # Complex regex
```

**Best Practices:**
- Start broad, refine based on false positives
- Use non-capturing groups for efficiency: `(?:str|int)`
- Test patterns with regex tools before deployment
- Include common variations

### Detection Methods

Filter by how mistake was detected:

```yaml
trigger:
  detection_methods:
    - "runtime_error"      # Exceptions during execution
    - "tool_failure"       # Read, Grep, Bash failures
    - "test_failure"       # pytest, jest failures
    - "build_failure"      # Compilation errors
    - "lint_failure"       # Linter warnings
```

### File Patterns

Limit to specific file types or paths:

```yaml
trigger:
  file_patterns:
    - "*.py"                          # Python files
    - "**/*.ts"                       # TypeScript (recursive)
    - "src/api/**/*.py"               # Specific directory
    - "!tests/**"                     # Exclude tests (negation)
```

## Resolution Steps

### Action Types

```yaml
resolution_steps:
  - id: step_1
    action: read              # Read files
    description: "..."

  - id: step_2
    action: grep              # Search codebase
    description: "..."

  - id: step_3
    action: edit              # Modify files
    description: "..."

  - id: step_4
    action: execute           # Run commands
    description: "..."

  - id: step_5
    action: verify            # Check success
    description: "..."
```

### Timeout Tiers

Choose appropriate timeout for each step:

```yaml
resolution_steps:
  - action: read
    timeout_tier: instant     # 5 seconds - File reads
    timeout_seconds: 5

  - action: grep
    timeout_tier: fast        # 30 seconds - Simple searches
    timeout_seconds: 30

  - action: edit
    timeout_tier: fast        # 30 seconds - File edits
    timeout_seconds: 30

  - action: execute
    timeout_tier: standard    # 120 seconds - Tests, builds
    timeout_seconds: 120

  - action: deploy
    timeout_tier: long        # 600 seconds - Deployments
    timeout_seconds: 600

  - action: background
    timeout_tier: background  # 0 seconds - Async (callback)
    timeout_seconds: 0
```

### Conditional Steps

Use context to make steps conditional:

```yaml
resolution_steps:
  - id: check_python_version
    action: execute
    description: "Check Python version"
    command: "python3 --version"
    timeout_tier: instant
    conditions:
      - file_pattern: "*.py"

  - id: run_typescript_check
    action: execute
    description: "Run TypeScript compiler"
    command: "tsc --noEmit"
    timeout_tier: standard
    conditions:
      - file_pattern: "*.ts"
```

### Parameterized Steps

Use placeholders for dynamic values:

```yaml
resolution_steps:
  - id: fix_import
    action: edit
    description: "Fix import statement in {{file_path}}"
    file_path: "{{context.file_path}}"
    find: "from {{context.old_module}}"
    replace: "from {{context.new_module}}"
    timeout_tier: fast
```

## Success Criteria

Define what constitutes successful resolution:

```yaml
success_criteria:
  no_new_errors: true                # No new errors introduced
  type_check_passes: true            # Type checker passes
  lint_passes: true                  # Linter passes
  tests_pass: true                   # Tests pass
  build_succeeds: true               # Build succeeds

  custom_checks:
    - name: "API still responds"
      command: "curl -f http://localhost:8000/health"
      timeout: 10

    - name: "Database migration applied"
      command: "python manage.py showmigrations | grep '\[X\]'"
      timeout: 5
```

## Metadata

Track playbook usage and health:

```yaml
metadata:
  # Set at creation
  confidence: 0.95                   # Initial confidence (0.0-1.0)
  root_cause: "knowledge_gap"        # Root cause category
  created_at: "2026-01-21T10:00:00Z" # Creation timestamp
  created_by: "rca_001"              # RCA result ID

  # Updated automatically
  usage_count: 0                     # Times executed
  success_count: 0                   # Successful executions
  failure_count: 0                   # Failed executions
  success_rate: 0.0                  # success_count / usage_count
  last_used: null                    # Last execution timestamp
  last_success: null                 # Last successful execution
  last_failure: null                 # Last failed execution

  # Lifecycle management
  lifecycle_state: "ACTIVE"          # ACTIVE, NEEDS_REVALIDATION, ARCHIVED
  needs_revalidation: false          # Flagged for review
  archived_at: null                  # Archival timestamp
  archive_reason: null               # Why archived
```

## Generation from RCA

Automatically generate playbooks from RCA results:

```python
from lib.playbook_generator import PlaybookGenerator
from lib.mistake_rca import MistakeRCA

# Run RCA
rca = MistakeRCA()
result = await rca.analyze_mistake(
    mistake_id="mistake_001",
    error_message="TypeError: expected dict, got str",
    context={...}
)

# Generate playbook
generator = PlaybookGenerator()
playbook = generator.generate(
    rca_result=result,
    playbook_name="Fix TypeError in function calls"
)

# Save to file
path = generator.save(
    playbook=playbook,
    output_dir="/home/pook/engineer-team/playbooks"
)

print(f"Playbook saved: {path}")
```

## Three-Layer Customization

Customize playbooks at three levels:

### Global Layer (Defaults)

`/home/pook/engineer-team/playbooks/global/type-error-fix.yaml`
```yaml
id: type-error-fix
description: "Fix TypeError exceptions"
timeout: fast
severity: medium
min_confidence: 0.7
```

### Project-Type Layer (Language-Specific)

`/home/pook/engineer-team/playbooks/python/type-error-fix.yaml`
```yaml
# Inherits from global, adds Python-specific
timeout: fast          # Inherited from global
severity: high         # Override
max_retries: 2         # New field
verification_command: "pyright {{file_path}}"
```

### Local Layer (Project-Specific)

`.playbooks/type-error-fix.yaml` (in project root)
```yaml
# Final overrides for this project
min_confidence: 0.95   # Stricter than default
max_retries: 1         # Conservative retries
notification_slack: "#dev-alerts"
```

## Inheritance with "extends"

Inherit from base playbooks:

```yaml
# Base playbook: playbooks/global/base-error-fix.yaml
id: base-error-fix
severity: medium
timeout: standard
max_retries: 3

# Extended playbook: playbooks/python/type-error-fix.yaml
id: type-error-fix
extends: base-error-fix     # Inherit from base
severity: high              # Override
max_retries: 2              # Override
verification: pyright       # New field
```

Resolution order:
1. Resolve `base-error-fix`
2. Merge `type-error-fix` on top
3. Apply project-type layer (if exists)
4. Apply local layer (if exists)

## Validation

Validate playbook structure before deployment:

```bash
# Validate single playbook
python3 playbooks/validate_playbooks.py playbooks/pb_*.yaml

# Validate all playbooks
python3 playbooks/validate_playbooks.py playbooks/**/*.yaml

# Strict validation (fail on warnings)
python3 playbooks/validate_playbooks.py --strict playbooks/pb_*.yaml
```

**Checks performed:**
- YAML syntax valid
- Required fields present (`id`, `trigger`, `resolution_steps`)
- Trigger patterns are valid regex
- Timeout tiers are valid
- Success criteria defined
- Metadata complete

## Testing Playbooks

Test playbooks in isolation before production:

```python
from lib.playbook_executor import PlaybookExecutor
import yaml

# Load playbook
with open('playbooks/pb_test.yaml') as f:
    playbook = yaml.safe_load(f)

# Execute in dry-run mode
executor = PlaybookExecutor()
result = await executor.execute(
    playbook=playbook,
    context={
        "error_message": "TypeError: expected dict, got str",
        "file_path": "test_module.py"
    },
    dry_run=True  # Don't actually make changes
)

# Check results
print(f"Would execute {len(result.steps)} steps")
for step in result.steps:
    print(f"  {step.id}: {step.description}")
```

## Best Practices

### 1. Start Specific, Broaden Carefully

```yaml
# Good - Specific pattern
trigger:
  patterns:
    - "TypeError: expected dict, got (str|int|list)"
  file_patterns:
    - "src/api/**/*.py"

# Bad - Too broad
trigger:
  patterns:
    - "Error"  # Matches everything
```

### 2. Use Descriptive IDs and Names

```yaml
# Good
id: fix-type-error-in-api-handlers
name: "Fix TypeError in API request handlers"

# Bad
id: pb_001
name: "Fix error"
```

### 3. Order Steps Logically

```yaml
resolution_steps:
  - id: analyze        # 1. Understand the problem
  - id: locate         # 2. Find affected code
  - id: fix            # 3. Make changes
  - id: verify         # 4. Confirm success
```

### 4. Set Realistic Timeouts

```yaml
# Good - Realistic for operation
- action: execute
  description: "Run full test suite"
  timeout_tier: long
  timeout_seconds: 600

# Bad - Too short
- action: execute
  description: "Run full test suite"
  timeout_tier: instant
  timeout_seconds: 5
```

### 5. Define Clear Success Criteria

```yaml
# Good - Measurable criteria
success_criteria:
  no_new_errors: true
  type_check_passes: true
  tests_pass: true

# Bad - Vague
success_criteria:
  looks_good: true
```

### 6. Version Control Playbooks

```bash
# Add to git
git add playbooks/pb_*.yaml
git commit -m "Add playbook for TypeError fixes"

# Track changes
git log --follow playbooks/pb_specific.yaml
```

### 7. Monitor Performance

```python
# Track execution metrics
{
    "playbook_id": "pb_a21ad52afbd2",
    "avg_duration": 45.6,
    "success_rate": 0.89,
    "p95_duration": 78.2
}

# Optimize slow steps
if step.duration > step.timeout_seconds * 0.8:
    logger.warning(f"Step {step.id} near timeout")
```

## Common Patterns

### Pattern 1: Type Error Fix

```yaml
id: type-error-fix
trigger:
  patterns: ["TypeError"]
resolution_steps:
  - action: read        # Read function signature
  - action: grep        # Find call sites
  - action: edit        # Fix type mismatches
  - action: verify      # Run type checker
```

### Pattern 2: Import Error Fix

```yaml
id: import-error-fix
trigger:
  patterns: ["ImportError", "ModuleNotFoundError"]
resolution_steps:
  - action: grep        # Find import statements
  - action: edit        # Fix import path
  - action: execute     # Test import
```

### Pattern 3: Null Reference Fix

```yaml
id: null-reference-fix
trigger:
  patterns: ["NoneType.*has no attribute"]
resolution_steps:
  - action: read        # Read assignment
  - action: edit        # Add null check
  - action: verify      # Confirm no NoneType errors
```

## Troubleshooting

### Playbook Not Triggering

Check pattern matching:
```bash
# Test regex patterns
python3 -c "
import re
pattern = 'expected.*got'
text = 'TypeError: expected dict, got str'
print(re.search(pattern, text))
"
```

### Steps Timing Out

Increase timeout tier or optimize step:
```yaml
# Before
timeout_tier: fast
timeout_seconds: 30

# After
timeout_tier: standard
timeout_seconds: 120
```

### Low Success Rate

Add more verification steps:
```yaml
success_criteria:
  no_new_errors: true
  type_check_passes: true
  tests_pass: true          # Add test verification
  custom_checks:            # Add specific checks
    - name: "API responds"
      command: "curl -f http://localhost:8000/health"
```

## Next Steps

- **[Playbook Lifecycle](lifecycle.md)** - Understand aging and archival
- **[Best Practices](best-practices.md)** - Advanced techniques
- **[API Reference](../api-reference.md)** - Trigger playbooks via API
