# Self-Learning Mistake System (Blazing Buffalo)

The Blazing Buffalo self-learning mistake system automatically detects, analyzes, and learns from mistakes to prevent similar issues in the future.

## Overview

Blazing Buffalo is an autonomous system that:

1. **Detects mistakes** from tool failures, runtime errors, and test failures
2. **Analyzes root causes** using multi-model RCA (Claude, Gemini, GLM)
3. **Generates playbooks** with automated resolution steps
4. **Executes playbooks** when similar mistakes occur
5. **Learns continuously** through confidence decay and revalidation

## System Flow

```
┌────────────────────────────────────────────────────────────────┐
│  1. MISTAKE DETECTION                                          │
│  • Tool failures (Read, Grep, Bash errors)                     │
│  • Runtime errors (exceptions, type errors)                    │
│  • Test failures (pytest, jest)                                │
└────────────────────────────────────────────────────────────────┘
                            ↓
┌────────────────────────────────────────────────────────────────┐
│  2. ROOT CAUSE ANALYSIS (Multi-Model RCA)                      │
│  • Context extraction (code, conversation, similar mistakes)   │
│  • Pattern detection via dynamic taxonomy                      │
│  • Multi-model convergence (Claude → Gemini → GLM)            │
│  • Prevention rule generation                                  │
└────────────────────────────────────────────────────────────────┘
                            ↓
┌────────────────────────────────────────────────────────────────┐
│  3. PLAYBOOK GENERATION                                        │
│  • Trigger pattern creation (regex, file patterns)             │
│  • Resolution steps with timeout tiers                         │
│  • Success criteria definition                                 │
│  • YAML export with metadata                                   │
└────────────────────────────────────────────────────────────────┘
                            ↓
┌────────────────────────────────────────────────────────────────┐
│  4. PLAYBOOK EXECUTION                                         │
│  • Pattern matching against new mistakes                       │
│  • Step-by-step execution with circuit breaker                 │
│  • Success/failure tracking                                    │
│  • Metadata updates (usage_count, success_rate)                │
└────────────────────────────────────────────────────────────────┘
                            ↓
┌────────────────────────────────────────────────────────────────┐
│  5. LIFECYCLE MANAGEMENT                                       │
│  • Confidence decay (unused playbooks)                         │
│  • Revalidation (high failure rate)                            │
│  • Archival (very old or low confidence)                       │
└────────────────────────────────────────────────────────────────┘
```

## Key Features

### Multi-Model Root Cause Analysis
- **Claude** - Deep reasoning and pattern recognition
- **Gemini** - Cross-validation and alternative perspectives
- **GLM** - Convergence checking and consensus building

### Dynamic Taxonomy
- Automatic mistake clustering using HDBSCAN
- Evolving categories based on new mistakes
- Semantic similarity via Qdrant vector search

### Three-Layer Playbook Resolution
- **Global layer** - Defaults for all projects
- **Project-type layer** - Language-specific (Python, TypeScript, Go, Rust, Java)
- **Local layer** - Project-specific customizations

### Timeout Tiers
- **INSTANT** (5s) - Read, Grep operations
- **FAST** (30s) - Edit, simple Bash commands
- **STANDARD** (120s) - Build, test operations
- **LONG** (600s) - Deploy, migrations
- **BACKGROUND** (0s) - Async operations with callback

### Circuit Breaker Protection
- 5 consecutive failures → Open circuit
- Exponential backoff (5s → 600s)
- Prevents cascading failures

## Storage Architecture

### Neo4j Graph Database
Stores mistake relationships and lineage:

```cypher
(Mistake)-[:ANALYZED_BY]->(RCAResult)
(RCAResult)-[:GENERATED]->(Playbook)
(Playbook)-[:RESOLVED]->(Mistake)
(Mistake)-[:SIMILAR_TO]->(Mistake)
(Mistake)-[:BELONGS_TO]->(TaxonomyCluster)
```

### Qdrant Vector Database
Semantic similarity search:

- **Collection**: `mistakes`
- **Vectors**: 384-dimensional embeddings (SentenceTransformer)
- **Payload**: Mistake metadata, error messages, context

### Local YAML Files
Playbook storage:

```
/home/pook/engineer-team/playbooks/
├── global/              # Defaults for all projects
├── python/              # Python-specific
├── typescript/          # TypeScript-specific
├── go/                  # Go-specific
├── rust/                # Rust-specific
└── archived/            # Old/low-confidence playbooks
```

## Quick Links

- **[Getting Started](getting-started.md)** - Install and create your first playbook
- **[Architecture](architecture.md)** - Deep dive into system design
- **[API Reference](api-reference.md)** - REST endpoints and examples
- **[Playbook Guide](playbooks/creating.md)** - Create and manage playbooks
- **[Runbooks](runbooks/circuit-breaker-open.md)** - Operational procedures
- **[Troubleshooting](troubleshooting.md)** - Common issues and solutions

## Metrics

### System Health
- **Mistake detection rate** - Mistakes detected per hour
- **RCA completion rate** - Successful RCA analyses / Total mistakes
- **Playbook match rate** - Mistakes matched to playbooks / Total mistakes
- **Playbook success rate** - Successful resolutions / Playbook executions
- **Circuit breaker status** - Open/closed/half-open per playbook

### Playbook Health
- **Confidence score** - 0.0-1.0 (decays with age)
- **Usage count** - Times playbook has been executed
- **Success rate** - Successful executions / Total executions
- **Last used** - Timestamp of last execution
- **Lifecycle state** - ACTIVE, NEEDS_REVALIDATION, ARCHIVED

## Example Use Case

**Mistake**: TypeError when calling function with wrong argument type

```python
# Code
def process(data: dict):
    return data.get("key")

# Error
process("wrong_type")  # TypeError: 'str' object has no attribute 'get'
```

**System Response**:

1. **Detection** - Tool failure captured
2. **RCA** - Multi-model analysis identifies: Knowledge gap about type annotations
3. **Playbook Generation** - Creates `type-error-fix.yaml` with:
   - Trigger: `TypeError`, `type.*error`
   - Steps: Verify types → Trace origin → Fix type mismatch → Verify
4. **Next Occurrence** - Playbook auto-executes and fixes similar TypeError
5. **Learning** - Success rate tracked, confidence maintained

## Getting Help

- **Documentation issues** - File issues on GitHub
- **Questions** - Check [Troubleshooting](troubleshooting.md)
- **API errors** - See [API Reference](api-reference.md#errors)
- **Playbook issues** - See [Playbook Lifecycle](playbooks/lifecycle.md)
