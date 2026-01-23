# Troubleshooting

Common issues and solutions for the Blazing Buffalo self-learning mistake system.

## Connection Issues

### Neo4j Connection Failed

**Symptoms:**
```
neo4j.exceptions.ServiceUnavailable: Failed to establish connection to ('localhost', 7687)
```

**Solutions:**

1. **Check Neo4j is running:**
```bash
docker ps | grep neo4j
# If not running:
docker compose up -d neo4j
```

2. **Verify credentials:**
```bash
# Test connection
python3 -c "
from neo4j import GraphDatabase
driver = GraphDatabase.driver(
    'bolt://localhost:7687',
    auth=('neo4j', 'your_password')
)
driver.verify_connectivity()
"
```

3. **Reset Neo4j password:**
```bash
docker exec -it neo4j cypher-shell -u neo4j -p password
> ALTER USER neo4j SET PASSWORD 'new_password';
```

4. **Check firewall:**
```bash
sudo ufw allow 7687/tcp
```

---

### Qdrant Connection Failed

**Symptoms:**
```
ConnectionError: Cannot connect to Qdrant at localhost:6333
```

**Solutions:**

1. **Check Qdrant is running:**
```bash
docker ps | grep qdrant
# If not running:
docker compose up -d qdrant
```

2. **Verify collection exists:**
```bash
curl http://localhost:6333/collections/mistakes
```

3. **Recreate collection:**
```bash
python3 scripts/setup-qdrant-mistakes.py
```

4. **Check logs:**
```bash
docker logs qdrant
```

---

## API Issues

### Rate Limit Exceeded

**Symptoms:**
```json
{
  "error": {
    "code": "RATE_LIMITED",
    "message": "Rate limit exceeded"
  }
}
```

**Solutions:**

1. **Check current limits:**
```bash
curl -I http://localhost:8200/mistakes
# Look for X-RateLimit-* headers
```

2. **Increase limits (config/settings.py):**
```python
api_rate_limit: int = 200  # Increase from 100
api_rate_limit_burst: int = 40  # Increase from 20
```

3. **Wait for reset:**
```python
import time
import requests

response = requests.get("http://localhost:8200/mistakes")
if response.status_code == 429:
    reset_time = int(response.headers.get('X-RateLimit-Reset', 0))
    wait_seconds = reset_time - int(time.time())
    print(f"Wait {wait_seconds} seconds")
    time.sleep(wait_seconds)
```

---

### API Not Responding

**Symptoms:**
```
curl: (7) Failed to connect to localhost port 8200
```

**Solutions:**

1. **Check API is running:**
```bash
ps aux | grep mistake_routes
# Or with Docker:
docker ps | grep mistake-api
```

2. **Check logs:**
```bash
tail -f /var/log/blazing_buffalo.log
# Or Docker:
docker logs mistake-api
```

3. **Restart API:**
```bash
# Standalone:
pkill -f mistake_routes
uvicorn services.api.mistake_routes:router --host 0.0.0.0 --port 8200

# Docker:
docker compose restart mistake-api
```

---

## RCA Issues

### RCA Timeout

**Symptoms:**
```json
{
  "error": {
    "code": "RCA_FAILED",
    "message": "RCA analysis timed out after 120 seconds"
  }
}
```

**Solutions:**

1. **Increase timeout (.env):**
```bash
RCA_TIMEOUT_SECONDS=300  # Increase from 120
```

2. **Check model availability:**
```python
from ralph import Ralph

ralph = Ralph()
# Test each model
for model in ["claude", "gemini", "glm"]:
    try:
        result = ralph.analyze("test", model=model, timeout=10)
        print(f"{model}: OK")
    except Exception as e:
        print(f"{model}: FAILED - {e}")
```

3. **Reduce context size:**
```python
# Limit similar mistakes
context = {
    "similar_mistakes": similar[:3],  # Reduce from 5 to 3
    "conversation_history": messages[-5:]  # Reduce from 10 to 5
}
```

---

### Low RCA Confidence

**Symptoms:**
```json
{
  "rca_result": {
    "confidence": 0.45,
    "models_used": ["claude", "gemini", "glm"],
    "agreement_score": 0.52
  }
}
```

**Solutions:**

1. **Provide more context:**
```python
context = {
    "code_snippet": full_function,  # Not just error line
    "surrounding_code": file_content,
    "recent_changes": git_diff,
    "similar_mistakes": similar_ids,
    "conversation_history": messages
}
```

2. **Check model agreement:**
```python
# If models disagree, investigate why
if rca_result.agreement_score < 0.8:
    for model_result in rca_result.model_results:
        print(f"{model_result.model}: {model_result.root_cause}")
    # Manual review may be needed
```

3. **Lower threshold (temporarily):**
```bash
RCA_MIN_CONFIDENCE=0.6  # Lower from 0.8
```

---

## Playbook Issues

### Playbook Not Triggering

**Symptoms:**
- Mistake detected but no playbook executed
- API returns no matching playbooks

**Solutions:**

1. **Check trigger patterns:**
```bash
# Test regex pattern
python3 -c "
import re
pattern = 'TypeError.*expected.*got'
text = 'TypeError: expected dict, got str'
match = re.search(pattern, text, re.IGNORECASE)
print('Match:', bool(match))
"
```

2. **Check file patterns:**
```yaml
# Ensure file matches playbook file_patterns
trigger:
  file_patterns:
    - "*.py"  # Matches Python files
    - "!tests/**"  # But not test files
```

3. **Check confidence threshold:**
```python
# Playbook confidence must be >= threshold
playbook_confidence = 0.65
threshold = 0.7  # Too high!

# Lower threshold or boost playbook confidence
```

4. **Verify playbook is ACTIVE:**
```bash
grep "lifecycle_state" playbooks/pb_*.yaml
# Should be "ACTIVE", not "ARCHIVED"
```

---

### Playbook Timing Out

**Symptoms:**
```json
{
  "execution_id": "exec_001",
  "status": "failed",
  "error": "Step 'analyze' timed out after 5 seconds"
}
```

**Solutions:**

1. **Increase timeout tier:**
```yaml
# Before
- id: analyze
  timeout_tier: instant  # 5s
  timeout_seconds: 5

# After
- id: analyze
  timeout_tier: fast  # 30s
  timeout_seconds: 30
```

2. **Optimize step:**
```yaml
# Bad - Reads entire codebase
- action: grep
  pattern: "error"
  path: "."  # Too broad

# Good - Specific path
- action: grep
  pattern: "error"
  path: "src/api"  # Narrower scope
```

3. **Split into smaller steps:**
```yaml
# Instead of one long step:
- id: full_analysis
  timeout_tier: long

# Split into multiple fast steps:
- id: analyze_imports
  timeout_tier: fast
- id: analyze_types
  timeout_tier: fast
- id: analyze_usage
  timeout_tier: fast
```

---

### Circuit Breaker Open

**Symptoms:**
```json
{
  "error": {
    "code": "CIRCUIT_OPEN",
    "message": "Circuit breaker is open for playbook pb_a21ad52afbd2"
  }
}
```

**Solutions:**

1. **Check failure history:**
```bash
curl http://localhost:8200/playbooks/pb_a21ad52afbd2/circuit-breaker
```

2. **Investigate failures:**
```bash
# Check last execution logs
grep "pb_a21ad52afbd2" /var/log/blazing_buffalo.log | tail -20
```

3. **Fix underlying issue** (then reset):
```bash
# Reset circuit breaker
curl -X POST http://localhost:8200/playbooks/pb_a21ad52afbd2/circuit-breaker/reset \
  -H "Content-Type: application/json" \
  -d '{"reason": "Fixed timeout issue", "confirmed": true}'
```

4. **Adjust threshold:**
```bash
# Increase tolerance (.env)
CIRCUIT_BREAKER_THRESHOLD=10  # Increase from 5
```

---

## Lifecycle Issues

### Playbook Unexpectedly Archived

**Symptoms:**
- Playbook moved to `playbooks/archived/`
- No longer auto-executing

**Solutions:**

1. **Check archive reason:**
```bash
grep -A 5 "archive_reason" playbooks/archived/pb_old.yaml
```

2. **Restore if needed:**
```bash
# Move back to active
mv playbooks/archived/pb_old.yaml playbooks/

# Update metadata
python3 -c "
import yaml
with open('playbooks/pb_old.yaml') as f:
    pb = yaml.safe_load(f)
pb['metadata']['lifecycle_state'] = 'ACTIVE'
pb['metadata']['confidence'] = 0.8
del pb['metadata']['archived_at']
del pb['metadata']['archive_reason']
with open('playbooks/pb_old.yaml', 'w') as f:
    yaml.dump(pb, f)
"
```

3. **Adjust thresholds:**
```python
# lib/playbook_lifecycle.py
ARCHIVE_DAYS = 365  # Increase from 180
MIN_CONFIDENCE = 0.2  # Lower from 0.3
```

---

### Confidence Decaying Too Fast

**Symptoms:**
- Playbook confidence drops from 0.9 to 0.3 in weeks
- Too many revalidation requests

**Solutions:**

1. **Increase decay period:**
```python
# lib/playbook_lifecycle.py
CONFIDENCE_DECAY_DAYS = 60  # Increase from 30
```

2. **Reduce decay amount:**
```python
CONFIDENCE_DECAY_AMOUNT = 0.05  # Reduce from 0.1
```

3. **Use playbook more frequently:**
```python
# Confidence recovers with successful executions
# Each success: +0.05 confidence
```

---

## Performance Issues

### Slow Qdrant Searches

**Symptoms:**
```
Similar mistake search took 5+ seconds
```

**Solutions:**

1. **Check collection size:**
```bash
curl http://localhost:6333/collections/mistakes
# Look at "points_count"
```

2. **Optimize HNSW parameters:**
```python
client.update_collection(
    collection_name="mistakes",
    hnsw_config=models.HnswConfigDiff(
        m=32,  # Increase from 16
        ef_construct=200  # Increase from 100
    )
)
```

3. **Add payload indexes:**
```python
client.create_payload_index(
    collection_name="mistakes",
    field_name="detection_method",
    field_schema="keyword"
)
```

---

### Slow Neo4j Queries

**Symptoms:**
```
Cypher query took 10+ seconds
```

**Solutions:**

1. **Create indexes:**
```cypher
CREATE INDEX mistake_timestamp IF NOT EXISTS
FOR (m:Mistake) ON (m.timestamp);

CREATE INDEX playbook_confidence IF NOT EXISTS
FOR (p:Playbook) ON (p.confidence);
```

2. **Optimize query:**
```cypher
// Bad - No index usage
MATCH (m:Mistake)
WHERE m.timestamp > datetime('2026-01-01')
RETURN m;

// Good - Uses index
MATCH (m:Mistake)
WHERE m.timestamp > datetime('2026-01-01')
USING INDEX m:Mistake(timestamp)
RETURN m;
```

3. **Limit results:**
```cypher
MATCH (m:Mistake)
RETURN m
LIMIT 100  // Add limit
```

---

## Data Issues

### Missing Similar Mistakes

**Symptoms:**
- RCA finds 0 similar mistakes
- Qdrant search returns empty

**Solutions:**

1. **Check embeddings exist:**
```bash
curl http://localhost:6333/collections/mistakes/points/mistake_001
```

2. **Regenerate embeddings:**
```python
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient

model = SentenceTransformer('all-MiniLM-L6-v2')
client = QdrantClient(host="localhost", port=6333)

# Get mistake
mistake = get_mistake("mistake_001")

# Generate embedding
embedding = model.encode(mistake.error_message)

# Upsert to Qdrant
client.upsert(
    collection_name="mistakes",
    points=[{
        "id": mistake.id,
        "vector": embedding.tolist(),
        "payload": mistake.dict()
    }]
)
```

3. **Lower similarity threshold:**
```python
# Find similar with lower threshold
similar = await rca.find_similar(
    mistake_id="mistake_001",
    min_similarity=0.5  # Lower from 0.7
)
```

---

### Playbook Validation Errors

**Symptoms:**
```
ValidationError: trigger.patterns is required
```

**Solutions:**

1. **Check required fields:**
```yaml
# Minimum required fields
id: my-playbook
trigger:
  patterns:
    - "error_pattern"
resolution_steps:
  - id: step_1
    action: read
    timeout_tier: instant
success_criteria:
  no_new_errors: true
metadata:
  confidence: 0.8
```

2. **Validate before deploying:**
```bash
python3 playbooks/validate_playbooks.py playbooks/my-playbook.yaml
```

3. **Check YAML syntax:**
```bash
yamllint playbooks/my-playbook.yaml
```

---

## Debugging Tips

### Enable Debug Logging

```python
# config/logging.py
LOG_LEVEL = "DEBUG"

# Or environment variable
export LOG_LEVEL=DEBUG
```

### Trace Specific Request

```python
import logging

logger = logging.getLogger("lib.mistake_rca")
logger.setLevel(logging.DEBUG)

# Now trace RCA
result = await rca.analyze_mistake(...)
```

### Dry Run Mode

```python
# Test playbook without making changes
result = await executor.execute(
    playbook=playbook,
    context=context,
    dry_run=True  # No actual changes
)
```

### Manual RCA Test

```python
from lib.mistake_rca import MistakeRCA
import asyncio

async def test_rca():
    rca = MistakeRCA()
    result = await rca.analyze_mistake(
        mistake_id="test_001",
        error_message="TypeError: expected dict, got str",
        context={
            "code_snippet": "def process(data: dict):\n    return data.get('key')",
            "file_path": "test.py"
        }
    )
    print(f"Root cause: {result.root_cause}")
    print(f"Confidence: {result.confidence}")
    print(f"Prevention: {result.prevention_rule}")

asyncio.run(test_rca())
```

## Getting Help

### Check Documentation
- [Architecture](architecture.md) - System design
- [API Reference](api-reference.md) - API details
- [Configuration](configuration.md) - Settings

### Collect Diagnostic Info

```bash
# System info
python3 --version
docker --version
docker compose ps

# Service status
curl http://localhost:8200/health
curl http://localhost:6333/collections/mistakes
docker exec neo4j cypher-shell -u neo4j -p password "MATCH (n) RETURN count(n);"

# Recent logs
tail -100 /var/log/blazing_buffalo.log

# Configuration
cat .env | grep -v PASSWORD
```

### File Issue

Include:
- Error message and stack trace
- Steps to reproduce
- Configuration (without secrets)
- Log excerpts
- System info

## Next Steps

- **[Runbooks](runbooks/circuit-breaker-open.md)** - Step-by-step procedures
- **[Configuration](configuration.md)** - Adjust settings
- **[API Reference](api-reference.md)** - API debugging
