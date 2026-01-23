# Configuration

Configure the Blazing Buffalo self-learning mistake system for your environment.

## Environment Variables

Create a `.env` file in `/home/pook/engineer-team`:

```bash
# Neo4j Configuration
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_secure_password
NEO4J_DATABASE=neo4j

# Qdrant Configuration
QDRANT_HOST=localhost
QDRANT_PORT=6333
QDRANT_COLLECTION=mistakes
QDRANT_VECTOR_SIZE=384

# Playbook Configuration
PLAYBOOK_DIR=/home/pook/engineer-team/playbooks
PLAYBOOK_CONFIDENCE_THRESHOLD=0.7
PLAYBOOK_MAX_RETRIES=3
PLAYBOOK_DEFAULT_TIMEOUT=120

# RCA Configuration
RCA_MODELS=claude,gemini,glm
RCA_TIMEOUT_SECONDS=120
RCA_MIN_CONFIDENCE=0.8
RCA_AGREEMENT_THRESHOLD=0.8

# Circuit Breaker
CIRCUIT_BREAKER_THRESHOLD=5
CIRCUIT_BREAKER_TIMEOUT=300
CIRCUIT_BREAKER_HALF_OPEN_REQUESTS=3

# API Configuration
API_HOST=0.0.0.0
API_PORT=8200
API_RATE_LIMIT=100
API_RATE_LIMIT_BURST=20

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json
LOG_FILE=/var/log/blazing_buffalo.log

# Lifecycle Management
LIFECYCLE_CONFIDENCE_DECAY_DAYS=30
LIFECYCLE_CONFIDENCE_DECAY_AMOUNT=0.1
LIFECYCLE_REVALIDATION_DAYS=90
LIFECYCLE_ARCHIVE_DAYS=180
LIFECYCLE_MIN_CONFIDENCE=0.3
LIFECYCLE_MAX_FAILURE_RATE=0.3
```

## Python Configuration

Edit `config/settings.py`:

```python
from pydantic import BaseSettings
from typing import List

class Settings(BaseSettings):
    # Neo4j
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str
    neo4j_database: str = "neo4j"

    # Qdrant
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection: str = "mistakes"
    qdrant_vector_size: int = 384

    # Playbooks
    playbook_dir: str = "/home/pook/engineer-team/playbooks"
    playbook_confidence_threshold: float = 0.7
    playbook_max_retries: int = 3
    playbook_default_timeout: int = 120

    # RCA
    rca_models: List[str] = ["claude", "gemini", "glm"]
    rca_timeout_seconds: int = 120
    rca_min_confidence: float = 0.8
    rca_agreement_threshold: float = 0.8

    # Circuit Breaker
    circuit_breaker_threshold: int = 5
    circuit_breaker_timeout: int = 300
    circuit_breaker_half_open_requests: int = 3

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8200
    api_rate_limit: int = 100
    api_rate_limit_burst: int = 20

    # Logging
    log_level: str = "INFO"
    log_format: str = "json"
    log_file: str = "/var/log/blazing_buffalo.log"

    # Lifecycle
    lifecycle_confidence_decay_days: int = 30
    lifecycle_confidence_decay_amount: float = 0.1
    lifecycle_revalidation_days: int = 90
    lifecycle_archive_days: int = 180
    lifecycle_min_confidence: float = 0.3
    lifecycle_max_failure_rate: float = 0.3

    class Config:
        env_file = ".env"

settings = Settings()
```

## Docker Configuration

### docker-compose.yml

```yaml
version: '3.8'

services:
  neo4j:
    image: neo4j:5.15
    ports:
      - "7474:7474"  # HTTP
      - "7687:7687"  # Bolt
    environment:
      NEO4J_AUTH: neo4j/your_password
      NEO4J_PLUGINS: '["apoc"]'
    volumes:
      - neo4j_data:/data
      - neo4j_logs:/logs

  qdrant:
    image: qdrant/qdrant:v1.7.0
    ports:
      - "6333:6333"  # HTTP API
      - "6334:6334"  # gRPC
    volumes:
      - qdrant_data:/qdrant/storage

  mistake-api:
    build: .
    ports:
      - "8200:8200"
    depends_on:
      - neo4j
      - qdrant
    environment:
      NEO4J_URI: bolt://neo4j:7687
      NEO4J_PASSWORD: your_password
      QDRANT_HOST: qdrant
      QDRANT_PORT: 6333
    volumes:
      - ./playbooks:/app/playbooks
      - ./logs:/app/logs

volumes:
  neo4j_data:
  neo4j_logs:
  qdrant_data:
```

## Playbook Defaults

### Global Settings

`playbooks/config.yaml`:

```yaml
# Default playbook settings
defaults:
  timeout:
    instant: 5
    fast: 30
    standard: 120
    long: 600
    background: 0

  retries:
    max: 3
    backoff: exponential
    base_delay: 5

  circuit_breaker:
    threshold: 5
    timeout: 300
    half_open_requests: 3

  lifecycle:
    confidence_decay_days: 30
    confidence_decay_amount: 0.1
    min_confidence: 0.3
    revalidation_days: 90
    archive_days: 180

  verification:
    run_type_check: true
    run_linter: true
    run_tests: false  # Optional, slower
```

## RCA Settings

### Multi-Model Configuration

```python
# config/rca_settings.py
RCA_CONFIG = {
    "models": {
        "claude": {
            "model": "claude-sonnet-4-5",
            "temperature": 0.3,
            "max_tokens": 4000,
            "timeout": 60
        },
        "gemini": {
            "model": "gemini-2.0-flash-exp",
            "temperature": 0.3,
            "max_tokens": 4000,
            "timeout": 60
        },
        "glm": {
            "model": "glm-4-plus",
            "temperature": 0.3,
            "max_tokens": 4000,
            "timeout": 60
        }
    },

    "convergence": {
        "agreement_threshold": 0.8,
        "min_models": 2,
        "max_iterations": 3
    },

    "context": {
        "max_similar_mistakes": 5,
        "min_similarity": 0.7,
        "include_conversation": True,
        "max_conversation_messages": 10
    }
}
```

## Logging Configuration

### Structured Logging

```python
# config/logging.py
import logging
import structlog

def configure_logging():
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(
        format="%(message)s",
        level=logging.INFO,
        handlers=[
            logging.FileHandler("/var/log/blazing_buffalo.log"),
            logging.StreamHandler()
        ]
    )
```

### Log Levels

```yaml
# config/log_levels.yaml
loggers:
  lib.mistake_rca:
    level: DEBUG
    handlers: [file, console]

  lib.playbook_executor:
    level: INFO
    handlers: [file, console]

  services.api.mistake_routes:
    level: INFO
    handlers: [file]

  lib.playbook_lifecycle:
    level: WARNING
    handlers: [file]
```

## Rate Limiting

### API Rate Limits

```python
# config/rate_limits.py
RATE_LIMITS = {
    "/mistakes": {
        "limit": 100,
        "period": 60,  # seconds
        "burst": 20
    },
    "/playbooks/execute": {
        "limit": 10,
        "period": 60,
        "burst": 2
    },
    "/rca/analyze": {
        "limit": 20,
        "period": 60,
        "burst": 5
    }
}
```

## Monitoring Configuration

### Prometheus Metrics

```yaml
# config/prometheus.yml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'blazing_buffalo'
    static_configs:
      - targets: ['localhost:8200']
    metrics_path: '/metrics'
```

### Grafana Dashboard

```json
{
  "dashboard": {
    "title": "Blazing Buffalo Metrics",
    "panels": [
      {
        "title": "Mistake Detection Rate",
        "targets": [
          {
            "expr": "rate(mistakes_detected_total[5m])"
          }
        ]
      },
      {
        "title": "Playbook Success Rate",
        "targets": [
          {
            "expr": "playbook_success_rate"
          }
        ]
      },
      {
        "title": "RCA Duration",
        "targets": [
          {
            "expr": "histogram_quantile(0.95, rca_duration_seconds_bucket)"
          }
        ]
      },
      {
        "title": "Circuit Breaker Status",
        "targets": [
          {
            "expr": "circuit_breaker_open"
          }
        ]
      }
    ]
  }
}
```

## Security Configuration

### API Authentication

```python
# config/auth.py
from fastapi import Security, HTTPException
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(name="X-API-Key")

async def verify_api_key(api_key: str = Security(api_key_header)):
    if api_key not in VALID_API_KEYS:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return api_key
```

### Input Validation

```python
# config/validation.py
from pydantic import BaseModel, validator

class MistakeCreate(BaseModel):
    error_message: str
    source: str
    detection_method: str

    @validator('error_message')
    def validate_error_message(cls, v):
        if len(v) < 10:
            raise ValueError('Error message too short')
        if len(v) > 10000:
            raise ValueError('Error message too long')
        return v

    @validator('source')
    def validate_source(cls, v):
        # Prevent path traversal
        if '..' in v:
            raise ValueError('Invalid source path')
        return v
```

## Database Configuration

### Neo4j Indexes

```cypher
-- Create indexes for performance
CREATE INDEX mistake_timestamp IF NOT EXISTS
FOR (m:Mistake) ON (m.timestamp);

CREATE INDEX mistake_detection_method IF NOT EXISTS
FOR (m:Mistake) ON (m.detection_method);

CREATE INDEX playbook_confidence IF NOT EXISTS
FOR (p:Playbook) ON (p.confidence);

CREATE INDEX playbook_lifecycle_state IF NOT EXISTS
FOR (p:Playbook) ON (p.lifecycle_state);
```

### Qdrant Collection Setup

```python
# config/qdrant_setup.py
from qdrant_client import QdrantClient
from qdrant_client.http import models

def setup_qdrant_collection():
    client = QdrantClient(host="localhost", port=6333)

    client.create_collection(
        collection_name="mistakes",
        vectors_config=models.VectorParams(
            size=384,
            distance=models.Distance.COSINE
        ),
        optimizers_config=models.OptimizersConfigDiff(
            indexing_threshold=10000,
            memmap_threshold=20000
        ),
        hnsw_config=models.HnswConfigDiff(
            m=16,
            ef_construct=100,
            full_scan_threshold=10000
        )
    )

    # Create payload indexes
    client.create_payload_index(
        collection_name="mistakes",
        field_name="detection_method",
        field_schema="keyword"
    )

    client.create_payload_index(
        collection_name="mistakes",
        field_name="root_cause",
        field_schema="keyword"
    )
```

## Performance Tuning

### Connection Pooling

```python
# config/connections.py
from neo4j import AsyncGraphDatabase

async def get_neo4j_driver():
    driver = AsyncGraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
        max_connection_pool_size=50,
        connection_acquisition_timeout=30.0
    )
    return driver
```

### Caching

```python
# config/cache.py
from functools import lru_cache

@lru_cache(maxsize=1000)
def get_playbook(playbook_id: str):
    # Cache playbook lookups
    with open(f"playbooks/{playbook_id}.yaml") as f:
        return yaml.safe_load(f)
```

## Development vs Production

### Development Settings

```python
# config/dev_settings.py
class DevSettings(Settings):
    log_level: str = "DEBUG"
    playbook_confidence_threshold: float = 0.5  # Lower threshold
    rca_timeout_seconds: int = 300  # Longer timeout
    circuit_breaker_threshold: int = 10  # More tolerant
```

### Production Settings

```python
# config/prod_settings.py
class ProdSettings(Settings):
    log_level: str = "WARNING"
    playbook_confidence_threshold: float = 0.8  # Higher threshold
    rca_timeout_seconds: int = 60  # Stricter timeout
    circuit_breaker_threshold: int = 3  # Less tolerant
```

## Validation

Validate configuration before starting:

```bash
# Validate environment
python3 -m config.validate

# Check Neo4j connection
python3 -c "
from neo4j import GraphDatabase
driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', 'password'))
driver.verify_connectivity()
print('✓ Neo4j connected')
"

# Check Qdrant connection
python3 -c "
from qdrant_client import QdrantClient
client = QdrantClient(host='localhost', port=6333)
print(client.get_collections())
print('✓ Qdrant connected')
"

# Validate playbook directory
python3 playbooks/validate_playbooks.py playbooks/**/*.yaml
```

## Next Steps

- **[Getting Started](getting-started.md)** - Install and configure
- **[API Reference](api-reference.md)** - API configuration options
- **[Troubleshooting](troubleshooting.md)** - Configuration issues
