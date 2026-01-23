# Blazing Buffalo 🦬🔥

Self-Learning Mistake System for AI Agent Ecosystems

## Overview

Blazing Buffalo enables AI agent systems to **learn from their mistakes** through automated capture, analysis, prevention, and continuous improvement.

### The Problem
- 36 specialized agents but no ability to learn from errors
- Mistakes repeat because there's no institutional knowledge
- No feedback loop between detection and prevention

### The Solution
A 5-layer self-learning system:

```
Session Hooks → Mistake Detector → Correction Verifier
                      ↓
              Dynamic Taxonomy → Attribution Scorer
                      ↓
              RCA Pipeline (Claude→Gemini→GLM)
                      ↓
              Playbook Generator → Conflict Detector
                      ↓
              Playbook Executor ← Circuit Breaker
                      ↓
              Effectiveness Tracker → A/B Testing
```

## Key Features

- **Mistake Detection**: 5 detection signals (user corrections, tool errors, test failures, lint errors, explicit flags)
- **Dynamic Taxonomy**: Emergent clustering with 0.8 similarity threshold
- **Multi-Agent Attribution**: 5 roles (originator, amplifier, propagator, detector, resolver)
- **RCA Pipeline**: Ralph multi-model consensus (Claude→Gemini→GLM)
- **Playbook System**: Auto-generated with lifecycle management (decay, revalidation, archive)
- **Circuit Breaker**: 3-state pattern preventing cascade failures
- **Rate Limiting**: Multi-window (10/min, 100/hr, 500/day)
- **Audit Logging**: Fernet encryption, RBAC, SOC2/ISO27001 ready

## Performance

| Metric | Result | Target |
|--------|--------|--------|
| API Throughput | 15,390 req/s | 500 req/s |
| P99 Latency | 20.9ms | 200ms |
| Error Rate | 0.00% | <1% |

## Project Structure

```
blazing-buffalo/
├── lib/                    # Core libraries
│   ├── correction_verifier.py
│   ├── dynamic_taxonomy.py
│   ├── attribution.py
│   ├── mistake_rca.py
│   ├── playbook_*.py
│   ├── circuit_breaker.py
│   ├── rate_limiter.py
│   ├── effectiveness_tracker.py
│   ├── audit_logger.py
│   └── metrics.py
├── services/
│   ├── api/               # REST API (10 endpoints)
│   └── dashboard/         # Web UI (WCAG AAA)
├── tests/                 # 400+ unit tests
├── monitoring/            # 21 Prometheus alerts
├── scripts/               # Backup/restore (RPO 24h, RTO 2h)
└── docs/                  # MkDocs documentation
```

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run tests
pytest tests/

# Start API server
uvicorn services.api.mistake_routes:app --reload
```

## Documentation

See `docs/self-learning/` for comprehensive documentation including:
- Getting Started Guide
- Architecture Overview
- API Reference
- Playbook Creation Guide
- Operational Runbooks

## License

Private - All rights reserved

---

*Built with Ralph-Wiggum multi-model orchestration (6 iterations, 0.92 final confidence)*
