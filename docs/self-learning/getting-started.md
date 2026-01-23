# Getting Started with Blazing Buffalo

Get up and running with the self-learning mistake system in minutes.

## Prerequisites

- Python 3.11+
- Docker (for Neo4j and Qdrant)
- 4GB RAM minimum
- 10GB disk space

## Installation

### 1. Start Required Services

```bash
# Start Neo4j and Qdrant
cd ~/engineer-team
docker compose up -d neo4j qdrant

# Verify services are running
docker ps | grep -E "(neo4j|qdrant)"
```

### 2. Initialize Vector Database

```bash
# Create Qdrant collection for mistakes
python3 scripts/setup-qdrant-mistakes.py

# Expected output:
# ✓ Collection 'mistakes' created
# ✓ Vector dimension: 384
# ✓ Distance metric: Cosine
```

### 3. Verify Neo4j Connection

```bash
# Check Neo4j is accessible
curl -u neo4j:password http://localhost:7474

# Run schema setup (if needed)
python3 migrations/test_001_mistake_schema.py
```

### 4. Start Mistake API

```bash
# Start the REST API server
cd ~/engineer-team
uvicorn services.api.mistake_routes:router --host 0.0.0.0 --port 8200

# Verify health
curl http://localhost:8200/health
```

## Quick Start: Your First Playbook

### Step 1: Detect a Mistake

The system automatically detects mistakes from:
- Tool failures (Read, Grep, Bash errors)
- Runtime exceptions
- Test failures

Or manually submit a mistake:

```bash
curl -X POST http://localhost:8200/mistakes \
  -H "Content-Type: application/json" \
  -d '{
    "error_message": "TypeError: expected dict, got str",
    "source": "my_module.py",
    "context": {
      "code_snippet": "def process(data: dict):\n    return data.get(\"key\")",
      "stack_trace": "line 42 in process"
    },
    "detection_method": "runtime_error"
  }'
```

### Step 2: Run Root Cause Analysis

```python
from lib.mistake_rca import MistakeRCA
import asyncio

async def analyze():
    rca = MistakeRCA()

    # Run RCA on mistake
    result = await rca.analyze_mistake(
        mistake_id="mistake_001",
        error_message="TypeError: expected dict, got str",
        context={
            "code_snippet": "def process(data: dict):\n    return data.get('key')",
            "project_path": "/home/pook/my_project"
        }
    )

    print(f"Root Cause: {result.root_cause}")
    print(f"Confidence: {result.confidence}")
    print(f"Prevention Rule: {result.prevention_rule}")

asyncio.run(analyze())
```

### Step 3: Generate Playbook

```python
from lib.playbook_generator import PlaybookGenerator

# Initialize generator
generator = PlaybookGenerator()

# Generate from RCA result
playbook = generator.generate(
    rca_result=result,
    playbook_name="Fix TypeError in function calls"
)

# Save playbook
playbook_path = generator.save(
    playbook=playbook,
    output_dir="/home/pook/engineer-team/playbooks"
)

print(f"Playbook saved: {playbook_path}")
```

### Step 4: Verify Playbook

```bash
# Validate playbook structure
python3 playbooks/validate_playbooks.py playbooks/pb_*.yaml

# Expected output:
# ✓ pb_a21ad52afbd2.yaml is valid
# ✓ All trigger patterns are valid regex
# ✓ All timeout tiers are valid
# ✓ Success criteria defined
```

### Step 5: Execute Playbook

```bash
# Trigger playbook manually
curl -X POST http://localhost:8200/playbooks/execute \
  -H "Content-Type: application/json" \
  -d '{
    "playbook_id": "pb_a21ad52afbd2",
    "context": {
      "error_message": "TypeError: expected dict, got str",
      "file_path": "my_module.py"
    }
  }'

# Monitor execution
curl http://localhost:8200/playbooks/pb_a21ad52afbd2/status
```

## Understanding Playbook Structure

A generated playbook looks like this:

```yaml
id: pb_a21ad52afbd2
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
  - id: analyze_type_mismatch
    action: read
    description: "Read function signature and identify type mismatch"
    timeout_tier: instant
    timeout_seconds: 5

  - id: check_caller
    action: grep
    description: "Find where function is called incorrectly"
    timeout_tier: fast
    timeout_seconds: 30

  - id: fix_type
    action: edit
    description: "Fix argument type at call site"
    timeout_tier: fast
    timeout_seconds: 30

  - id: verify_fix
    action: verify
    description: "Run type checker to confirm fix"
    timeout_tier: fast
    timeout_seconds: 30

success_criteria:
  no_new_errors: true
  type_check_passes: true

metadata:
  confidence: 0.95
  root_cause: "knowledge_gap"
  created_at: "2026-01-21T10:30:00Z"
  usage_count: 0
  success_rate: 0.0
```

## Next Steps

### Customize Playbooks
Create project-specific overrides:

```bash
# Create local playbook directory
mkdir -p .playbooks

# Copy global playbook and customize
cp /home/pook/engineer-team/playbooks/global/type-error-fix.yaml \
   .playbooks/type-error-fix.yaml

# Edit with project-specific settings
vim .playbooks/type-error-fix.yaml
```

### Monitor System Health

```bash
# Check mistake stats
curl http://localhost:8200/stats

# List recent mistakes
curl http://localhost:8200/mistakes?limit=10

# Check playbook health
curl http://localhost:8200/playbooks/stats
```

### Set Up Automation

```bash
# Add cron job for playbook maintenance
echo "0 2 * * * cd /home/pook/engineer-team && python3 scripts/playbook_maintenance.py" | crontab -

# Set up continuous mistake detection (if using agents)
# Agents automatically submit mistakes to the system
```

## Configuration

### Environment Variables

Create `.env` file:

```bash
# Neo4j
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password

# Qdrant
QDRANT_HOST=localhost
QDRANT_PORT=6333
QDRANT_COLLECTION=mistakes

# Playbook Settings
PLAYBOOK_DIR=/home/pook/engineer-team/playbooks
PLAYBOOK_CONFIDENCE_THRESHOLD=0.7
PLAYBOOK_MAX_RETRIES=3

# RCA Settings
RCA_MODELS=claude,gemini,glm
RCA_TIMEOUT_SECONDS=120
RCA_MIN_CONFIDENCE=0.8

# Circuit Breaker
CIRCUIT_BREAKER_THRESHOLD=5
CIRCUIT_BREAKER_TIMEOUT=300
```

### Adjust Lifecycle Thresholds

Edit `lib/playbook_lifecycle.py`:

```python
class PlaybookLifecycleManager:
    CONFIDENCE_DECAY_DAYS = 30      # Days between decay
    CONFIDENCE_DECAY_AMOUNT = 0.1   # Amount to decay
    REVALIDATION_DAYS = 90          # Days until revalidation
    ARCHIVE_DAYS = 180              # Days until archival
    MIN_CONFIDENCE = 0.3            # Minimum confidence
    MAX_FAILURE_RATE = 0.3          # Maximum failure rate
```

## Troubleshooting

### Qdrant Connection Failed

```bash
# Check Qdrant is running
docker ps | grep qdrant

# Restart Qdrant
docker restart qdrant

# Verify collection exists
curl http://localhost:6333/collections/mistakes
```

### Neo4j Authentication Error

```bash
# Reset Neo4j password
docker exec -it neo4j cypher-shell -u neo4j -p password
> ALTER USER neo4j SET PASSWORD 'new_password';
```

### Playbook Not Executing

Check circuit breaker status:

```bash
curl http://localhost:8200/playbooks/pb_*/circuit-breaker

# If open, reset circuit breaker
curl -X POST http://localhost:8200/playbooks/pb_*/circuit-breaker/reset
```

### Low RCA Confidence

Increase context quality:

```python
# Provide more context to RCA
context = {
    "code_snippet": full_function,
    "surrounding_code": file_content,
    "recent_changes": git_diff,
    "similar_mistakes": similar_ids,
    "conversation_history": last_10_messages
}
```

## Learn More

- **[Architecture](architecture.md)** - System design and data flow
- **[API Reference](api-reference.md)** - Complete REST API documentation
- **[Playbook Guide](playbooks/creating.md)** - Advanced playbook techniques
- **[Configuration](configuration.md)** - Detailed configuration options
