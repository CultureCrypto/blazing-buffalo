# API Reference

Complete REST API documentation for the Blazing Buffalo self-learning mistake system.

## Base URL

```
http://localhost:8200
```

## Authentication

Currently using IP-based rate limiting. Future versions will support API keys.

## Rate Limits

- **Default**: 100 requests/minute per IP
- **Burst**: 20 requests/second
- **Headers**: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`

## Endpoints

### Health Check

#### GET /health

Check API health status.

**Response**
```json
{
  "status": "healthy",
  "service": "mistake-api",
  "version": "1.0.0",
  "timestamp": "2026-01-21T10:00:00Z"
}
```

---

### Mistakes

#### GET /mistakes

List all mistakes with pagination.

**Query Parameters**
- `limit` (integer, default: 50, max: 200) - Number of results
- `offset` (integer, default: 0) - Pagination offset
- `detection_method` (string, optional) - Filter by detection method
- `source` (string, optional) - Filter by source file
- `since` (ISO8601, optional) - Mistakes after timestamp

**Example Request**
```bash
curl "http://localhost:8200/mistakes?limit=10&detection_method=runtime_error"
```

**Response**
```json
{
  "mistakes": [
    {
      "id": "mistake_001",
      "error_message": "TypeError: expected dict, got str",
      "source": "my_module.py",
      "detection_method": "runtime_error",
      "timestamp": "2026-01-21T10:00:00Z",
      "context": {
        "code_snippet": "def process(data: dict):\n    return data.get('key')",
        "stack_trace": "line 42 in process"
      },
      "rca_id": "rca_001",
      "playbook_id": "pb_a21ad52afbd2"
    }
  ],
  "total": 145,
  "limit": 10,
  "offset": 0
}
```

---

#### POST /mistakes

Create a new mistake entry.

**Request Body**
```json
{
  "error_message": "TypeError: expected dict, got str",
  "source": "my_module.py",
  "detection_method": "runtime_error",
  "context": {
    "code_snippet": "def process(data: dict):\n    return data.get('key')",
    "stack_trace": "line 42 in process",
    "file_path": "/home/pook/project/my_module.py",
    "line_number": 42
  }
}
```

**Response** (201 Created)
```json
{
  "id": "mistake_002",
  "status": "created",
  "rca_scheduled": true,
  "estimated_rca_time": "10-20s"
}
```

**Error Responses**
- `400 Bad Request` - Invalid request body
- `429 Too Many Requests` - Rate limit exceeded
- `500 Internal Server Error` - Server error

---

#### GET /mistakes/{mistake_id}

Get detailed information about a specific mistake.

**Path Parameters**
- `mistake_id` (string, required) - Mistake ID

**Example Request**
```bash
curl http://localhost:8200/mistakes/mistake_001
```

**Response**
```json
{
  "id": "mistake_001",
  "error_message": "TypeError: expected dict, got str",
  "source": "my_module.py",
  "detection_method": "runtime_error",
  "timestamp": "2026-01-21T10:00:00Z",
  "context": {...},
  "rca_result": {
    "id": "rca_001",
    "root_cause": "knowledge_gap",
    "confidence": 0.92,
    "prevention_rule": "Always use type annotations and verify at call sites",
    "models_used": ["claude", "gemini", "glm"]
  },
  "playbook": {
    "id": "pb_a21ad52afbd2",
    "name": "Fix TypeError in function calls",
    "last_executed": "2026-01-21T11:00:00Z",
    "execution_success": true
  }
}
```

---

#### GET /mistakes/{mistake_id}/similar

Find similar mistakes using vector search.

**Path Parameters**
- `mistake_id` (string, required) - Mistake ID

**Query Parameters**
- `limit` (integer, default: 5, max: 20) - Number of similar mistakes
- `min_similarity` (float, default: 0.7, range: 0.0-1.0) - Minimum similarity score

**Example Request**
```bash
curl "http://localhost:8200/mistakes/mistake_001/similar?limit=5&min_similarity=0.8"
```

**Response**
```json
{
  "similar_mistakes": [
    {
      "id": "mistake_042",
      "similarity": 0.95,
      "error_message": "TypeError: 'str' object has no attribute 'get'",
      "source": "other_module.py",
      "playbook_id": "pb_a21ad52afbd2"
    },
    {
      "id": "mistake_087",
      "similarity": 0.87,
      "error_message": "TypeError: argument must be dict, not str",
      "source": "utils.py",
      "playbook_id": "pb_a21ad52afbd2"
    }
  ]
}
```

---

### RCA (Root Cause Analysis)

#### POST /rca/analyze

Trigger RCA for a mistake.

**Request Body**
```json
{
  "mistake_id": "mistake_001",
  "context": {
    "code_snippet": "def process(data: dict):\n    return data.get('key')",
    "surrounding_code": "...",
    "project_path": "/home/pook/project",
    "recent_changes": "git diff output"
  },
  "force": false
}
```

**Response** (202 Accepted)
```json
{
  "status": "analyzing",
  "mistake_id": "mistake_001",
  "estimated_time": "10-20s",
  "check_status_url": "/rca/mistake_001/status"
}
```

---

#### GET /rca/{mistake_id}/status

Check RCA analysis status.

**Path Parameters**
- `mistake_id` (string, required) - Mistake ID

**Example Request**
```bash
curl http://localhost:8200/rca/mistake_001/status
```

**Response** (In Progress)
```json
{
  "status": "analyzing",
  "progress": 0.6,
  "current_step": "multi_model_convergence",
  "models_completed": ["claude", "gemini"],
  "models_pending": ["glm"]
}
```

**Response** (Completed)
```json
{
  "status": "completed",
  "rca_result": {
    "id": "rca_001",
    "root_cause": "knowledge_gap",
    "category": "type_error",
    "confidence": 0.92,
    "prevention_rule": "Always use type annotations and verify at call sites",
    "models_used": ["claude", "gemini", "glm"],
    "agreement_score": 0.89,
    "similar_mistakes": ["mistake_042", "mistake_087"],
    "cluster_id": "cluster_05"
  }
}
```

---

### Playbooks

#### GET /playbooks

List all playbooks.

**Query Parameters**
- `limit` (integer, default: 50, max: 200) - Number of results
- `state` (string, optional) - Filter by lifecycle state (ACTIVE, NEEDS_REVALIDATION, ARCHIVED)
- `min_confidence` (float, optional) - Minimum confidence score

**Example Request**
```bash
curl "http://localhost:8200/playbooks?state=ACTIVE&min_confidence=0.8"
```

**Response**
```json
{
  "playbooks": [
    {
      "id": "pb_a21ad52afbd2",
      "name": "Fix TypeError in function calls",
      "confidence": 0.92,
      "usage_count": 45,
      "success_rate": 0.89,
      "last_used": "2026-01-21T11:00:00Z",
      "lifecycle_state": "ACTIVE",
      "circuit_breaker_state": "CLOSED"
    }
  ],
  "total": 23,
  "limit": 50,
  "offset": 0
}
```

---

#### GET /playbooks/{playbook_id}

Get detailed playbook information.

**Path Parameters**
- `playbook_id` (string, required) - Playbook ID

**Example Request**
```bash
curl http://localhost:8200/playbooks/pb_a21ad52afbd2
```

**Response**
```json
{
  "id": "pb_a21ad52afbd2",
  "name": "Fix TypeError in function calls",
  "trigger": {
    "patterns": ["TypeError", "expected.*got"],
    "detection_methods": ["runtime_error", "tool_failure"],
    "file_patterns": ["*.py"]
  },
  "resolution_steps": [
    {
      "id": "analyze_type_mismatch",
      "action": "read",
      "description": "Read function signature and identify type mismatch",
      "timeout_tier": "instant",
      "timeout_seconds": 5
    },
    {
      "id": "check_caller",
      "action": "grep",
      "description": "Find where function is called incorrectly",
      "timeout_tier": "fast",
      "timeout_seconds": 30
    },
    {
      "id": "fix_type",
      "action": "edit",
      "description": "Fix argument type at call site",
      "timeout_tier": "fast",
      "timeout_seconds": 30
    },
    {
      "id": "verify_fix",
      "action": "verify",
      "description": "Run type checker to confirm fix",
      "timeout_tier": "fast",
      "timeout_seconds": 30
    }
  ],
  "success_criteria": {
    "no_new_errors": true,
    "type_check_passes": true
  },
  "metadata": {
    "confidence": 0.92,
    "root_cause": "knowledge_gap",
    "created_at": "2026-01-21T10:30:00Z",
    "usage_count": 45,
    "success_rate": 0.89,
    "last_used": "2026-01-21T11:00:00Z",
    "lifecycle_state": "ACTIVE"
  }
}
```

---

#### POST /playbooks/execute

Execute a playbook manually.

**Request Body**
```json
{
  "playbook_id": "pb_a21ad52afbd2",
  "context": {
    "error_message": "TypeError: expected dict, got str",
    "file_path": "my_module.py",
    "line_number": 42
  },
  "dry_run": false
}
```

**Response** (202 Accepted)
```json
{
  "execution_id": "exec_001",
  "status": "executing",
  "playbook_id": "pb_a21ad52afbd2",
  "estimated_time": "60-90s",
  "check_status_url": "/playbooks/executions/exec_001"
}
```

---

#### GET /playbooks/executions/{execution_id}

Get playbook execution status.

**Path Parameters**
- `execution_id` (string, required) - Execution ID

**Example Request**
```bash
curl http://localhost:8200/playbooks/executions/exec_001
```

**Response** (In Progress)
```json
{
  "execution_id": "exec_001",
  "playbook_id": "pb_a21ad52afbd2",
  "status": "executing",
  "current_step": 2,
  "total_steps": 4,
  "steps_completed": [
    {
      "step_id": "analyze_type_mismatch",
      "status": "success",
      "duration_seconds": 3.2
    },
    {
      "step_id": "check_caller",
      "status": "success",
      "duration_seconds": 15.7
    }
  ]
}
```

**Response** (Completed)
```json
{
  "execution_id": "exec_001",
  "playbook_id": "pb_a21ad52afbd2",
  "status": "success",
  "total_steps": 4,
  "duration_seconds": 67.3,
  "steps_completed": [
    {
      "step_id": "analyze_type_mismatch",
      "status": "success",
      "duration_seconds": 3.2,
      "output": "Type mismatch found at line 42"
    },
    {
      "step_id": "check_caller",
      "status": "success",
      "duration_seconds": 15.7,
      "output": "Found 3 incorrect call sites"
    },
    {
      "step_id": "fix_type",
      "status": "success",
      "duration_seconds": 28.1,
      "output": "Fixed 3 call sites"
    },
    {
      "step_id": "verify_fix",
      "status": "success",
      "duration_seconds": 20.3,
      "output": "Type check passed"
    }
  ],
  "success_criteria_met": true
}
```

---

#### GET /playbooks/{playbook_id}/circuit-breaker

Get circuit breaker status for a playbook.

**Path Parameters**
- `playbook_id` (string, required) - Playbook ID

**Example Request**
```bash
curl http://localhost:8200/playbooks/pb_a21ad52afbd2/circuit-breaker
```

**Response**
```json
{
  "playbook_id": "pb_a21ad52afbd2",
  "state": "CLOSED",
  "consecutive_failures": 0,
  "failure_threshold": 5,
  "last_failure": null,
  "timeout_seconds": 300,
  "next_retry": null
}
```

**Response** (Open Circuit)
```json
{
  "playbook_id": "pb_a21ad52afbd2",
  "state": "OPEN",
  "consecutive_failures": 5,
  "failure_threshold": 5,
  "last_failure": "2026-01-21T11:00:00Z",
  "timeout_seconds": 300,
  "next_retry": "2026-01-21T11:05:00Z"
}
```

---

#### POST /playbooks/{playbook_id}/circuit-breaker/reset

Reset circuit breaker (requires manual confirmation).

**Path Parameters**
- `playbook_id` (string, required) - Playbook ID

**Request Body**
```json
{
  "reason": "Issue fixed, safe to retry",
  "confirmed": true
}
```

**Response**
```json
{
  "playbook_id": "pb_a21ad52afbd2",
  "state": "CLOSED",
  "reset_at": "2026-01-21T11:10:00Z",
  "reset_by": "admin"
}
```

---

### Statistics & Metrics

#### GET /stats

Get system-wide statistics.

**Example Request**
```bash
curl http://localhost:8200/stats
```

**Response**
```json
{
  "mistakes": {
    "total": 1453,
    "today": 23,
    "this_week": 142,
    "by_detection_method": {
      "runtime_error": 789,
      "tool_failure": 456,
      "test_failure": 208
    },
    "by_root_cause": {
      "knowledge_gap": 521,
      "tool_misuse": 387,
      "pattern_violation": 312,
      "other": 233
    }
  },
  "playbooks": {
    "total": 23,
    "active": 18,
    "needs_revalidation": 3,
    "archived": 2,
    "average_confidence": 0.84,
    "average_success_rate": 0.87
  },
  "rca": {
    "total_analyses": 1453,
    "average_duration_seconds": 12.3,
    "average_confidence": 0.88,
    "model_agreement_rate": 0.92
  },
  "executions": {
    "total": 3421,
    "successful": 2987,
    "failed": 434,
    "success_rate": 0.87,
    "average_duration_seconds": 45.6
  }
}
```

---

#### GET /taxonomy/clusters

Get dynamic taxonomy clusters.

**Example Request**
```bash
curl http://localhost:8200/taxonomy/clusters
```

**Response**
```json
{
  "clusters": [
    {
      "id": "cluster_05",
      "label": "Type Errors",
      "member_count": 234,
      "centroid_vector": [...],
      "representative_mistakes": [
        {
          "id": "mistake_001",
          "error_message": "TypeError: expected dict, got str"
        },
        {
          "id": "mistake_042",
          "error_message": "TypeError: 'str' object has no attribute 'get'"
        }
      ]
    },
    {
      "id": "cluster_12",
      "label": "Import Errors",
      "member_count": 156,
      "centroid_vector": [...],
      "representative_mistakes": [...]
    }
  ],
  "total_clusters": 15,
  "noise_points": 23
}
```

---

## Error Responses

All error responses follow this format:

```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable error message",
    "details": {...}
  }
}
```

### Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `INVALID_REQUEST` | 400 | Invalid request body or parameters |
| `NOT_FOUND` | 404 | Resource not found |
| `RATE_LIMITED` | 429 | Rate limit exceeded |
| `RCA_FAILED` | 500 | RCA analysis failed |
| `PLAYBOOK_EXECUTION_FAILED` | 500 | Playbook execution failed |
| `CIRCUIT_OPEN` | 503 | Circuit breaker is open |
| `STORAGE_ERROR` | 500 | Neo4j or Qdrant error |
| `INTERNAL_ERROR` | 500 | Internal server error |

### Example Error Response

```json
{
  "error": {
    "code": "CIRCUIT_OPEN",
    "message": "Circuit breaker is open for playbook pb_a21ad52afbd2",
    "details": {
      "playbook_id": "pb_a21ad52afbd2",
      "consecutive_failures": 5,
      "next_retry": "2026-01-21T11:05:00Z"
    }
  }
}
```

---

## WebSocket API (Future)

Coming soon: Real-time updates for RCA progress and playbook execution.

```javascript
const ws = new WebSocket('ws://localhost:8200/ws/rca/mistake_001');

ws.onmessage = (event) => {
  const update = JSON.parse(event.data);
  console.log('RCA progress:', update.progress);
};
```

---

## SDK Examples

### Python

```python
import requests

class MistakeAPI:
    def __init__(self, base_url="http://localhost:8200"):
        self.base_url = base_url

    def create_mistake(self, error_message, source, detection_method, context):
        response = requests.post(
            f"{self.base_url}/mistakes",
            json={
                "error_message": error_message,
                "source": source,
                "detection_method": detection_method,
                "context": context
            }
        )
        response.raise_for_status()
        return response.json()

    def get_similar(self, mistake_id, limit=5):
        response = requests.get(
            f"{self.base_url}/mistakes/{mistake_id}/similar",
            params={"limit": limit}
        )
        response.raise_for_status()
        return response.json()

# Usage
api = MistakeAPI()
mistake = api.create_mistake(
    error_message="TypeError: expected dict, got str",
    source="my_module.py",
    detection_method="runtime_error",
    context={"line_number": 42}
)
print(f"Created: {mistake['id']}")
```

### cURL

```bash
# Create mistake
curl -X POST http://localhost:8200/mistakes \
  -H "Content-Type: application/json" \
  -d '{"error_message": "TypeError", "source": "test.py", "detection_method": "runtime_error"}'

# Execute playbook
curl -X POST http://localhost:8200/playbooks/execute \
  -H "Content-Type: application/json" \
  -d '{"playbook_id": "pb_a21ad52afbd2", "context": {"file_path": "test.py"}}'

# Get stats
curl http://localhost:8200/stats
```
