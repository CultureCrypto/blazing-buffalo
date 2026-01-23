# Architecture

Deep dive into the Blazing Buffalo self-learning mistake system architecture.

## System Components

```
┌─────────────────────────────────────────────────────────────────┐
│                     DETECTION LAYER                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ Tool Monitor │  │ Runtime Hook │  │  Test Runner │          │
│  │  (BB-002)    │  │   (BB-003)   │  │   (BB-004)   │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│                   STORAGE & INDEXING                             │
│  ┌──────────────────────────┐  ┌──────────────────────────┐    │
│  │       Neo4j Graph        │  │    Qdrant Vectors        │    │
│  │  • Mistake relationships │  │  • Semantic similarity   │    │
│  │  • RCA lineage           │  │  • Embeddings (384-dim)  │    │
│  │  • Playbook links        │  │  • Fast KNN search       │    │
│  └──────────────────────────┘  └──────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│                   ANALYSIS LAYER (BB-011)                        │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐    │
│  │  Claude  │ → │  Gemini  │ → │   GLM    │ → │ Converge │    │
│  │  (deep)  │   │ (cross)  │   │  (check) │   │  (final) │    │
│  └──────────┘   └──────────┘   └──────────┘   └──────────┘    │
│          Multi-Model RCA with Attribution (BB-010)               │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│                  GENERATION LAYER (BB-012)                       │
│  ┌──────────────────┐  ┌─────────────────┐                     │
│  │ Playbook         │  │ Jinja2 Template │                     │
│  │ Generator        │  │ (autoescape)    │                     │
│  └──────────────────┘  └─────────────────┘                     │
│  • Trigger patterns   • Timeout tiers   • Success criteria      │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│                 RESOLUTION LAYER (BB-017)                        │
│  ┌──────────────────────────────────────────────────────┐      │
│  │          Three-Layer Playbook Resolver               │      │
│  │  Global → Project-Type (python/ts/go) → Local        │      │
│  └──────────────────────────────────────────────────────┘      │
│           Deep merge with inheritance chains                    │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│                  EXECUTION LAYER (BB-013)                        │
│  ┌──────────────────┐  ┌──────────────────┐                    │
│  │ Playbook Engine  │  │ Circuit Breaker  │                    │
│  │ • Step runner    │  │ • Failure limit  │                    │
│  │ • Timeout enforce│  │ • Auto-recovery  │                    │
│  └──────────────────┘  └──────────────────┘                    │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│                  LIFECYCLE LAYER (BB-015)                        │
│  • Confidence decay (30 days → -0.1)                            │
│  • Revalidation (90 days or >30% failure)                       │
│  • Archival (180 days or <0.3 confidence)                       │
└─────────────────────────────────────────────────────────────────┘
```

## Data Flow

### 1. Mistake Detection → Storage

```python
# Detection
mistake = {
    "id": "mistake_001",
    "error_message": "TypeError: expected dict, got str",
    "source": "my_module.py",
    "detection_method": "runtime_error",
    "timestamp": "2026-01-21T10:00:00Z",
    "context": {...}
}

# Neo4j storage (graph relationships)
CREATE (m:Mistake {
    id: $id,
    error_message: $error_message,
    timestamp: $timestamp
})

# Qdrant storage (vector embedding)
embedding = sentence_transformer.encode(mistake["error_message"])
qdrant.upsert(
    collection_name="mistakes",
    points=[{
        "id": mistake["id"],
        "vector": embedding.tolist(),
        "payload": mistake
    }]
)
```

### 2. RCA Analysis

```python
# Context extraction
context = {
    "code_snippet": read_file(source),
    "surrounding_code": get_context(source, line_number),
    "similar_mistakes": qdrant.search(embedding, limit=5),
    "dynamic_cluster": taxonomy.assign_cluster(mistake),
    "conversation_history": get_recent_messages(10)
}

# Multi-model analysis
claude_analysis = await ralph.analyze(prompt, model="claude")
gemini_analysis = await ralph.analyze(prompt, model="gemini")
glm_analysis = await ralph.analyze(prompt, model="glm")

# Convergence check
if agreement_score(claude, gemini, glm) > 0.8:
    rca_result = merge_analyses([claude, gemini, glm])
else:
    rca_result = run_tiebreaker()

# Attribution (who/what caused it)
attribution = MistakeAttribution().attribute(mistake, rca_result)
```

### 3. Playbook Generation

```python
# Generate from RCA
playbook = PlaybookGenerator().generate(
    rca_result=rca_result,
    playbook_name=f"Fix {rca_result.category}"
)

# Structure
{
    "id": "pb_a21ad52afbd2",
    "name": "Fix TypeError in function calls",
    "trigger": {
        "patterns": extract_patterns(rca_result),
        "file_patterns": ["*.py"]
    },
    "resolution_steps": generate_steps(rca_result),
    "success_criteria": {
        "no_new_errors": True,
        "type_check_passes": True
    },
    "metadata": {
        "confidence": 0.95,
        "root_cause": rca_result.root_cause
    }
}
```

### 4. Three-Layer Resolution

```python
# Resolution order
resolver = PlaybookResolver()

# Layer 1: Global (defaults)
global_pb = load_yaml("playbooks/global/type-error-fix.yaml")
# {timeout: "fast", severity: "medium"}

# Layer 2: Project-type (language-specific)
python_pb = load_yaml("playbooks/python/type-error-fix.yaml")
# Merges: {timeout: "fast", severity: "high", max_retries: 2}

# Layer 3: Local (project-specific)
local_pb = load_yaml(".playbooks/type-error-fix.yaml")
# Final: {timeout: "fast", severity: "high", max_retries: 2, min_confidence: 0.95}

# Inheritance resolution
if playbook.get("extends"):
    base = resolver.resolve(playbook["extends"])
    playbook = deep_merge(base, playbook)

# Final resolved playbook
resolved = resolver.resolve("type-error-fix")
```

### 5. Execution with Circuit Breaker

```python
# Pattern matching
for playbook in playbooks:
    if matches_trigger(mistake, playbook.trigger):
        # Check circuit breaker
        if circuit_breaker.is_open(playbook.id):
            logger.warning(f"Circuit open for {playbook.id}")
            continue

        # Execute steps
        try:
            for step in playbook.resolution_steps:
                result = execute_step(
                    step,
                    timeout=step.timeout_seconds
                )
                if not result.success:
                    circuit_breaker.record_failure(playbook.id)
                    break
            else:
                circuit_breaker.record_success(playbook.id)
                update_metadata(playbook.id, success=True)
        except Exception as e:
            circuit_breaker.record_failure(playbook.id)
            logger.error(f"Playbook failed: {e}")

# Circuit breaker state machine
"""
CLOSED (working) --[5 failures]--> OPEN (stopped)
    ↑                                    ↓
    |                            [timeout expires]
    |                                    ↓
    +--[success]--  HALF_OPEN (testing) <-+
                         ↓
                    [failure]
"""
```

## Storage Schema

### Neo4j Graph Schema

```cypher
// Nodes
(:Mistake {
    id: STRING,
    error_message: STRING,
    source: STRING,
    detection_method: STRING,
    timestamp: DATETIME,
    context: MAP
})

(:RCAResult {
    id: STRING,
    mistake_id: STRING,
    root_cause: STRING,
    confidence: FLOAT,
    prevention_rule: STRING,
    models_used: LIST
})

(:Playbook {
    id: STRING,
    name: STRING,
    confidence: FLOAT,
    usage_count: INT,
    success_rate: FLOAT,
    last_used: DATETIME
})

(:TaxonomyCluster {
    id: STRING,
    label: STRING,
    centroid: LIST,
    member_count: INT
})

// Relationships
(Mistake)-[:ANALYZED_BY]->(RCAResult)
(RCAResult)-[:GENERATED]->(Playbook)
(Playbook)-[:RESOLVED]->(Mistake)
(Mistake)-[:SIMILAR_TO {similarity: FLOAT}]->(Mistake)
(Mistake)-[:BELONGS_TO]->(TaxonomyCluster)
(RCAResult)-[:ATTRIBUTED_TO {score: FLOAT}]->(Agent|User|Tool)
```

### Qdrant Collection Schema

```python
{
    "collection_name": "mistakes",
    "vectors": {
        "size": 384,
        "distance": "Cosine"
    },
    "payload_schema": {
        "id": "keyword",
        "error_message": "text",
        "source": "keyword",
        "detection_method": "keyword",
        "timestamp": "integer",
        "root_cause": "keyword",
        "cluster_id": "keyword",
        "tags": "keyword[]"
    }
}
```

## Component Details

### Multi-Model RCA (BB-011)

**Purpose**: Reduce hallucination through cross-validation

```python
class MistakeRCA:
    async def analyze_mistake(self, mistake_id, error_message, context):
        # 1. Extract context
        similar = await self.find_similar(error_message)
        cluster = self.taxonomy.assign_cluster(mistake_id)

        # 2. Multi-model analysis
        prompt = self.build_prompt(error_message, context, similar, cluster)

        claude_result = await self.ralph.analyze(prompt, model="claude")
        gemini_result = await self.ralph.analyze(prompt, model="gemini")
        glm_result = await self.ralph.analyze(prompt, model="glm")

        # 3. Convergence check
        agreement = self.check_agreement([claude, gemini, glm])

        if agreement > 0.8:
            # Models agree - high confidence
            final = self.merge_analyses([claude, gemini, glm])
        else:
            # Models disagree - need tiebreaker
            final = await self.run_tiebreaker([claude, gemini, glm])

        # 4. Attribution
        attribution = self.attribute_mistake(mistake_id, final)

        return RCAResult(
            root_cause=final.root_cause,
            confidence=final.confidence,
            prevention_rule=final.prevention_rule,
            models_used=["claude", "gemini", "glm"],
            attribution=attribution
        )
```

### Dynamic Taxonomy (BB-009)

**Purpose**: Evolving mistake categories without predefined labels

```python
class DynamicTaxonomy:
    def __init__(self):
        self.clusterer = hdbscan.HDBSCAN(
            min_cluster_size=5,
            metric='cosine'
        )

    def assign_cluster(self, mistake_id):
        # 1. Get embedding
        embedding = self.get_embedding(mistake_id)

        # 2. Find existing cluster or create new
        cluster_id = self.find_nearest_cluster(embedding)

        if cluster_id is None:
            # No similar cluster - create new
            cluster_id = self.create_cluster(embedding)

        # 3. Update cluster metadata
        self.update_cluster(cluster_id, embedding)

        return ClusterAssignment(
            cluster_id=cluster_id,
            similarity=0.85,
            label=self.generate_label(cluster_id)
        )

    def recompute_clusters(self):
        # Periodic recomputation as new mistakes arrive
        all_embeddings = self.load_all_embeddings()
        labels = self.clusterer.fit_predict(all_embeddings)

        # Update cluster assignments in Neo4j
        self.update_all_assignments(labels)
```

### Playbook Lifecycle (BB-015)

**Purpose**: Prevent stale playbooks from causing issues

```python
class PlaybookLifecycleManager:
    def check_playbook(self, playbook):
        # Age-based checks
        days_unused = (now - playbook["last_used"]).days

        if days_unused > 180 or playbook["confidence"] < 0.3:
            return LifecycleState.ARCHIVED

        if days_unused > 90 or playbook["success_rate"] < 0.7:
            return LifecycleState.NEEDS_REVALIDATION

        if days_unused > 30:
            # Apply confidence decay
            new_confidence = playbook["confidence"] - 0.1
            self.update_confidence(playbook["id"], new_confidence)

        return LifecycleState.ACTIVE

    def run_maintenance(self):
        events = []

        for playbook in self.list_playbooks():
            state = self.check_playbook(playbook)

            if state == LifecycleState.ARCHIVED:
                path = self.archive_playbook(playbook["id"])
                events.append(LifecycleEvent(
                    playbook_id=playbook["id"],
                    event_type="archived",
                    reason=f"Unused for {days_unused} days"
                ))

            elif state == LifecycleState.NEEDS_REVALIDATION:
                self.flag_revalidation(playbook["id"])
                events.append(LifecycleEvent(
                    playbook_id=playbook["id"],
                    event_type="revalidation_required",
                    reason=f"Success rate: {playbook['success_rate']}"
                ))

        return events
```

## Integration Points

### With Engineer Team Agents

```python
# Agents automatically report mistakes
@agent_decorator
async def execute_task(task):
    try:
        result = await perform_task(task)
    except Exception as e:
        # Auto-submit to mistake system
        mistake_id = await mistake_api.create_mistake({
            "error_message": str(e),
            "source": task.file,
            "detection_method": "agent_error",
            "context": {
                "task": task.to_dict(),
                "agent": agent_name,
                "stack_trace": traceback.format_exc()
            }
        })

        # System automatically runs RCA and generates playbook
        logger.info(f"Mistake submitted: {mistake_id}")

        raise
```

### With Knowledge Graph

```python
# Bidirectional sync with KG
def sync_to_knowledge_graph(mistake, rca_result, playbook):
    # Store in Neo4j
    kg.create_nodes([
        ("Mistake", mistake),
        ("RCAResult", rca_result),
        ("Playbook", playbook)
    ])

    kg.create_relationships([
        (mistake.id, "ANALYZED_BY", rca_result.id),
        (rca_result.id, "GENERATED", playbook.id)
    ])

    # Add to Qdrant
    embedding = embed(mistake.error_message)
    qdrant.upsert(
        collection_name="mistakes",
        points=[{
            "id": mistake.id,
            "vector": embedding,
            "payload": {**mistake, "rca_id": rca_result.id}
        }]
    )
```

## Performance Characteristics

### RCA Latency
- **Context extraction**: 100-500ms
- **Qdrant similarity search**: 10-50ms
- **Multi-model analysis**: 5-15s (parallel)
- **Convergence check**: 100-200ms
- **Total**: 5-20s per mistake

### Playbook Execution
- **Pattern matching**: 1-10ms per playbook
- **Step execution**: Varies by timeout tier
- **Metadata update**: 50-100ms
- **Circuit breaker check**: <1ms

### Storage
- **Neo4j write**: 10-50ms per node
- **Qdrant upsert**: 5-20ms per vector
- **YAML file write**: 1-5ms

### Scalability
- **Mistakes/hour**: 100-1000 (limited by RCA)
- **Playbook executions/hour**: 1000-10000
- **Storage**: 1KB per mistake, 5KB per playbook
- **Memory**: 100MB baseline + 1MB per 1000 mistakes

## Security Considerations

### Template Injection Prevention
```python
# Jinja2 autoescape enabled
env = Environment(
    loader=BaseLoader(),
    autoescape=select_autoescape(['yaml', 'yml'])
)

# User input automatically escaped
playbook = env.from_string(template).render(
    user_input=escape(user_input)
)
```

### Circuit Breaker Limits
- Prevents runaway executions
- Exponential backoff on failures
- Manual override required for reset

### Confidence Thresholds
- Minimum 0.7 confidence for auto-execution
- Manual approval required for <0.7
- Auto-archive at <0.3

## Monitoring & Observability

### Metrics Exposed
```python
# Prometheus metrics
mistake_detection_rate = Counter("mistakes_detected_total")
rca_duration = Histogram("rca_duration_seconds")
playbook_success_rate = Gauge("playbook_success_rate", ["playbook_id"])
circuit_breaker_state = Gauge("circuit_breaker_open", ["playbook_id"])
```

### Logging
```python
# Structured logging
logger.info("RCA completed", extra={
    "mistake_id": mistake_id,
    "root_cause": rca.root_cause,
    "confidence": rca.confidence,
    "models_used": rca.models_used,
    "duration_seconds": duration
})
```

### Alerting Rules
- Circuit breaker open for >1 hour
- RCA confidence <0.5 for >50% of mistakes
- Playbook success rate <50%
- Qdrant/Neo4j connection failures
