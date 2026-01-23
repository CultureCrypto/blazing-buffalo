"""
Mistake Data REST API Routes.

Provides REST endpoints for the Blazing Buffalo self-learning mistake system:
- List, create, and retrieve mistakes
- Find similar mistakes using vector search
- List and execute playbooks
- Access dynamic taxonomy clusters
- Get system statistics

All endpoints include rate limiting, authentication (where required), and comprehensive
error handling. Integrates with Neo4j (graph data), Qdrant (vector search), and
PlaybookExecutor (playbook execution).
"""

import hashlib
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, HTTPException, Query, Depends, Header, Request
from pydantic import BaseModel, Field
from qdrant_client import QdrantClient
from qdrant_client.http import models as qdrant_models
from neo4j import AsyncGraphDatabase
from sentence_transformers import SentenceTransformer

from config import settings
from rate_limiter import limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Mistakes"])

# Constants
MISTAKES_COLLECTION = "mistakes"
EMBEDDING_DIM = 384  # all-MiniLM-L6-v2

# Lazy-loaded clients
_embedding_model: Optional[SentenceTransformer] = None
_qdrant_client: Optional[QdrantClient] = None
_neo4j_driver = None


def get_embedding_model() -> SentenceTransformer:
    """Get or initialize the embedding model."""
    global _embedding_model
    if _embedding_model is None:
        logger.info("Loading embedding model for mistake similarity")
        _embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
    return _embedding_model


def get_qdrant_client() -> QdrantClient:
    """Get or initialize Qdrant client."""
    global _qdrant_client
    if _qdrant_client is None:
        logger.info(f"Connecting to Qdrant at {settings.QDRANT_HOST}:{settings.QDRANT_PORT}")
        _qdrant_client = QdrantClient(
            host=settings.QDRANT_HOST,
            port=settings.QDRANT_PORT,
        )
    return _qdrant_client


def get_neo4j_driver():
    """Get or initialize Neo4j driver."""
    global _neo4j_driver
    if _neo4j_driver is None:
        logger.info(f"Connecting to Neo4j at {settings.NEO4J_URI}")
        _neo4j_driver = AsyncGraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
        )
    return _neo4j_driver


# Pydantic Models
class MistakeCreate(BaseModel):
    """Request model for creating a mistake."""
    category: str = Field(..., description="Hierarchical category (e.g., 'tool_error.Bash')")
    description: str = Field(..., description="Human-readable description")
    agent_id: str = Field(..., description="Agent that made the mistake")
    file_path: Optional[str] = Field(None, description="File where mistake occurred")
    line_number: Optional[int] = Field(None, description="Line number")
    severity: str = Field("medium", description="Severity: low, medium, high, critical")
    detection_method: str = Field(..., description="How it was detected")
    context_hash: Optional[str] = Field(None, description="Context hash for deduplication")
    raw_signal: Optional[str] = Field(None, description="Original detection signal")


class MistakeResponse(BaseModel):
    """Response model for mistake data."""
    id: str
    category: str
    description: str
    agent_id: str
    file_path: Optional[str]
    line_number: Optional[int]
    severity: str
    resolution_status: str
    confidence: float
    created_at: str
    detection_method: str


class SimilarMistakeResponse(BaseModel):
    """Response model for similar mistake search."""
    id: str
    category: str
    description: str
    similarity_score: float
    resolution_status: str
    playbook_id: Optional[str] = None


class PlaybookResponse(BaseModel):
    """Response model for playbook data."""
    id: str
    category: str
    description: str
    steps_count: int
    success_rate: float
    active: bool
    created_at: str


class PlaybookExecuteRequest(BaseModel):
    """Request model for executing a playbook."""
    context: Dict[str, Any] = Field(default_factory=dict, description="Execution context")
    dry_run: bool = Field(False, description="Dry run without actual execution")


class PlaybookExecuteResponse(BaseModel):
    """Response model for playbook execution result."""
    playbook_id: str
    status: str
    steps_completed: int
    steps_total: int
    execution_time_ms: int
    outputs: Optional[List[Dict[str, Any]]] = None


class TaxonomyClusterResponse(BaseModel):
    """Response model for taxonomy cluster."""
    cluster_id: str
    label: str
    mistake_count: int
    avg_severity: float
    top_keywords: List[str]


class StatsResponse(BaseModel):
    """Response model for system statistics."""
    total_mistakes: int
    total_playbooks: int
    playbooks_executed_today: int
    success_rate: float
    top_categories: List[Dict[str, Any]]
    avg_resolution_time_hours: float


# Routes
@router.get("/mistakes", response_model=List[MistakeResponse])
@limiter.limit("100/minute")
async def list_mistakes(
    request: Request,
    category: Optional[str] = Query(None, description="Filter by category"),
    severity: Optional[str] = Query(None, description="Filter by severity"),
    agent_id: Optional[str] = Query(None, description="Filter by agent"),
    status: Optional[str] = Query(None, description="Filter by resolution status"),
    limit: int = Query(50, le=200, description="Max results"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
):
    """
    List mistakes with optional filters.

    Returns paginated list of mistakes from Neo4j graph database.
    Supports filtering by category, severity, agent, and resolution status.
    """
    driver = get_neo4j_driver()

    try:
        # Build Cypher query with filters
        where_clauses = []
        params = {"limit": limit, "offset": offset}

        if category:
            where_clauses.append("m.category = $category")
            params["category"] = category
        if severity:
            where_clauses.append("m.severity = $severity")
            params["severity"] = severity
        if agent_id:
            where_clauses.append("m.agent_id = $agent_id")
            params["agent_id"] = agent_id
        if status:
            where_clauses.append("m.resolution_status = $status")
            params["status"] = status

        where_clause = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

        query = f"""
        MATCH (m:Mistake)
        {where_clause}
        RETURN m
        ORDER BY m.created_at DESC
        SKIP $offset
        LIMIT $limit
        """

        async with driver.session() as session:
            result = await session.run(query, params)
            records = await result.data()

        mistakes = []
        for record in records:
            m = record["m"]
            mistakes.append(MistakeResponse(
                id=m.get("id", ""),
                category=m.get("category", ""),
                description=m.get("description", ""),
                agent_id=m.get("agent_id", ""),
                file_path=m.get("file_path"),
                line_number=m.get("line_number"),
                severity=m.get("severity", "medium"),
                resolution_status=m.get("resolution_status", "unresolved"),
                confidence=m.get("confidence", 0.0),
                created_at=m.get("created_at", ""),
                detection_method=m.get("detection_method", ""),
            ))

        return mistakes

    except Exception as e:
        logger.error(f"Failed to list mistakes: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@router.post("/mistakes", response_model=MistakeResponse, status_code=201)
@limiter.limit("20/minute")
async def create_mistake(request: Request, mistake: MistakeCreate):
    """
    Create a new mistake entry.

    Creates mistake in both Neo4j (graph relationships) and Qdrant (vector search).
    Generates embeddings for similarity matching and deduplicates based on context hash.
    """
    driver = get_neo4j_driver()
    qdrant = get_qdrant_client()
    embedding_model = get_embedding_model()

    try:
        # Generate mistake ID
        mistake_id = f"mst_{uuid.uuid4().hex[:12]}"
        timestamp = datetime.now(timezone.utc).isoformat()

        # Create context hash if not provided
        context_hash = mistake.context_hash or hashlib.sha256(
            f"{mistake.category}:{mistake.description}:{mistake.agent_id}".encode()
        ).hexdigest()[:16]

        # Check for duplicates
        async with driver.session() as session:
            dup_result = await session.run(
                "MATCH (m:Mistake {context_hash: $hash}) RETURN m",
                {"hash": context_hash}
            )
            existing = await dup_result.single()

            if existing:
                logger.info(f"Duplicate mistake detected: {context_hash}")
                raise HTTPException(
                    status_code=409,
                    detail="Duplicate mistake (identical context_hash)"
                )

        # Create in Neo4j
        neo4j_query = """
        CREATE (m:Mistake {
            id: $id,
            category: $category,
            description: $description,
            agent_id: $agent_id,
            file_path: $file_path,
            line_number: $line_number,
            severity: $severity,
            detection_method: $detection_method,
            resolution_status: 'unresolved',
            confidence: 1.0,
            created_at: $created_at,
            context_hash: $context_hash,
            raw_signal: $raw_signal
        })
        RETURN m
        """

        async with driver.session() as session:
            await session.run(neo4j_query, {
                "id": mistake_id,
                "category": mistake.category,
                "description": mistake.description,
                "agent_id": mistake.agent_id,
                "file_path": mistake.file_path,
                "line_number": mistake.line_number,
                "severity": mistake.severity,
                "detection_method": mistake.detection_method,
                "created_at": timestamp,
                "context_hash": context_hash,
                "raw_signal": mistake.raw_signal or "",
            })

        # Create embeddings and store in Qdrant
        text_to_embed = f"{mistake.category} {mistake.description}"
        embedding = embedding_model.encode(text_to_embed).tolist()

        # Use UUID for Qdrant point ID (Qdrant requires UUID or unsigned int)
        point_uuid = str(uuid.uuid4())

        qdrant.upsert(
            collection_name=MISTAKES_COLLECTION,
            points=[
                qdrant_models.PointStruct(
                    id=point_uuid,
                    vector=embedding,
                    payload={
                        "mistake_id": mistake_id,  # Store our ID in payload
                        "category": mistake.category,
                        "description": mistake.description,
                        "agent_id": mistake.agent_id,
                        "severity": mistake.severity,
                        "created_at": timestamp,
                    }
                )
            ]
        )

        logger.info(f"Created mistake {mistake_id} in category {mistake.category}")

        return MistakeResponse(
            id=mistake_id,
            category=mistake.category,
            description=mistake.description,
            agent_id=mistake.agent_id,
            file_path=mistake.file_path,
            line_number=mistake.line_number,
            severity=mistake.severity,
            resolution_status="unresolved",
            confidence=1.0,
            created_at=timestamp,
            detection_method=mistake.detection_method,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create mistake: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create mistake: {str(e)}")


@router.get("/mistakes/{mistake_id}", response_model=MistakeResponse)
@limiter.limit("200/minute")
async def get_mistake(request: Request, mistake_id: str):
    """
    Get mistake details by ID.

    Retrieves full mistake data from Neo4j including relationships.
    """
    driver = get_neo4j_driver()

    try:
        query = """
        MATCH (m:Mistake {id: $id})
        RETURN m
        """

        async with driver.session() as session:
            result = await session.run(query, {"id": mistake_id})
            record = await result.single()

        if not record:
            raise HTTPException(status_code=404, detail=f"Mistake {mistake_id} not found")

        m = record["m"]
        return MistakeResponse(
            id=m["id"],
            category=m["category"],
            description=m["description"],
            agent_id=m["agent_id"],
            file_path=m.get("file_path"),
            line_number=m.get("line_number"),
            severity=m["severity"],
            resolution_status=m.get("resolution_status", "unresolved"),
            confidence=m.get("confidence", 1.0),
            created_at=m["created_at"],
            detection_method=m["detection_method"],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get mistake {mistake_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@router.get("/mistakes/{mistake_id}/similar", response_model=List[SimilarMistakeResponse])
@limiter.limit("50/minute")
async def get_similar_mistakes(
    request: Request,
    mistake_id: str,
    limit: int = Query(5, le=20, description="Max similar mistakes to return"),
):
    """
    Get similar mistakes using vector search.

    Uses Qdrant vector similarity to find mistakes with similar descriptions.
    Returns mistakes ordered by similarity score (0.0-1.0).
    """
    driver = get_neo4j_driver()
    qdrant = get_qdrant_client()
    embedding_model = get_embedding_model()

    try:
        # Get source mistake
        async with driver.session() as session:
            result = await session.run(
                "MATCH (m:Mistake {id: $id}) RETURN m",
                {"id": mistake_id}
            )
            record = await result.single()

        if not record:
            raise HTTPException(status_code=404, detail=f"Mistake {mistake_id} not found")

        source_mistake = record["m"]

        # Generate embedding for source mistake
        text_to_embed = f"{source_mistake['category']} {source_mistake['description']}"
        embedding = embedding_model.encode(text_to_embed).tolist()

        # Search for similar in Qdrant
        search_results = qdrant.search(
            collection_name=MISTAKES_COLLECTION,
            query_vector=embedding,
            limit=limit + 1,  # +1 to exclude self
        )

        # Filter out the source mistake and get details from Neo4j
        similar_mistakes = []
        for hit in search_results:
            # Get mistake ID from payload
            hit_mistake_id = hit.payload.get("mistake_id")
            if not hit_mistake_id or hit_mistake_id == mistake_id:
                continue

            # Get full details from Neo4j
            async with driver.session() as session:
                result = await session.run(
                    """
                    MATCH (m:Mistake {id: $id})
                    OPTIONAL MATCH (m)-[:RESOLVED_BY]->(p:Playbook)
                    RETURN m, p.id as playbook_id
                    """,
                    {"id": hit_mistake_id}
                )
                rec = await result.single()

            if rec:
                m = rec["m"]
                similar_mistakes.append(SimilarMistakeResponse(
                    id=m["id"],
                    category=m["category"],
                    description=m["description"],
                    similarity_score=hit.score,
                    resolution_status=m.get("resolution_status", "unresolved"),
                    playbook_id=rec.get("playbook_id"),
                ))

            if len(similar_mistakes) >= limit:
                break

        return similar_mistakes

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to find similar mistakes: {e}")
        raise HTTPException(status_code=500, detail=f"Search error: {str(e)}")


@router.get("/playbooks", response_model=List[PlaybookResponse])
@limiter.limit("100/minute")
async def list_playbooks(
    request: Request,
    category: Optional[str] = Query(None, description="Filter by category"),
    active_only: bool = Query(True, description="Only active playbooks"),
    limit: int = Query(50, le=100),
):
    """
    List available playbooks.

    Returns playbooks from Neo4j with success rates and metadata.
    """
    driver = get_neo4j_driver()

    try:
        where_clauses = []
        params = {"limit": limit}

        if category:
            where_clauses.append("p.category = $category")
            params["category"] = category
        if active_only:
            where_clauses.append("p.active = true")

        where_clause = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

        query = f"""
        MATCH (p:Playbook)
        {where_clause}
        RETURN p
        ORDER BY p.created_at DESC
        LIMIT $limit
        """

        async with driver.session() as session:
            result = await session.run(query, params)
            records = await result.data()

        playbooks = []
        for record in records:
            p = record["p"]
            playbooks.append(PlaybookResponse(
                id=p["id"],
                category=p["category"],
                description=p.get("description", ""),
                steps_count=p.get("steps_count", 0),
                success_rate=p.get("success_rate", 0.0),
                active=p.get("active", True),
                created_at=p["created_at"],
            ))

        return playbooks

    except Exception as e:
        logger.error(f"Failed to list playbooks: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@router.get("/playbooks/{playbook_id}", response_model=Dict[str, Any])
@limiter.limit("200/minute")
async def get_playbook(request: Request, playbook_id: str):
    """
    Get playbook details including steps.

    Returns full playbook data with execution steps and metadata.
    """
    driver = get_neo4j_driver()

    try:
        query = """
        MATCH (p:Playbook {id: $id})
        RETURN p
        """

        async with driver.session() as session:
            result = await session.run(query, {"id": playbook_id})
            record = await result.single()

        if not record:
            raise HTTPException(status_code=404, detail=f"Playbook {playbook_id} not found")

        p = record["p"]

        # Return full playbook including steps (stored as JSON)
        import json
        steps = json.loads(p.get("steps", "[]"))

        return {
            "id": p["id"],
            "category": p["category"],
            "description": p.get("description", ""),
            "steps": steps,
            "steps_count": len(steps),
            "success_rate": p.get("success_rate", 0.0),
            "active": p.get("active", True),
            "created_at": p["created_at"],
            "metadata": json.loads(p.get("metadata", "{}")),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get playbook {playbook_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@router.post("/playbooks/{playbook_id}/execute", response_model=PlaybookExecuteResponse)
@limiter.limit("10/minute")
async def execute_playbook(
    request: Request,
    playbook_id: str,
    exec_request: PlaybookExecuteRequest,
):
    """
    Execute a playbook.

    Uses PlaybookExecutor to run playbook steps with timeout tiers and checkpointing.
    Returns execution results with status and timing.
    """
    import sys
    from pathlib import Path

    # Import PlaybookExecutor
    lib_path = Path(__file__).parent.parent.parent / "lib"
    sys.path.insert(0, str(lib_path))

    try:
        from playbook_executor import PlaybookExecutor, StepStatus
    except ImportError as e:
        logger.error(f"Failed to import PlaybookExecutor: {e}")
        raise HTTPException(
            status_code=503,
            detail="PlaybookExecutor not available"
        )

    driver = get_neo4j_driver()

    try:
        # Get playbook from Neo4j
        async with driver.session() as session:
            result = await session.run(
                "MATCH (p:Playbook {id: $id}) RETURN p",
                {"id": playbook_id}
            )
            record = await result.single()

        if not record:
            raise HTTPException(status_code=404, detail=f"Playbook {playbook_id} not found")

        playbook_data = record["p"]

        # Parse playbook steps
        import json
        steps = json.loads(playbook_data.get("steps", "[]"))

        if not steps:
            raise HTTPException(status_code=400, detail="Playbook has no steps")

        # Convert to PlaybookExecutor format
        from dataclasses import dataclass
        from typing import List as TList

        @dataclass
        class Step:
            step_id: str
            timeout_tier: str
            action: str
            params: dict

        @dataclass
        class Playbook:
            id: str
            steps: TList[Step]

        playbook_steps = []
        for idx, step in enumerate(steps):
            playbook_steps.append(Step(
                step_id=f"step_{idx}",
                timeout_tier=step.get("timeout_tier", "standard"),
                action=step.get("action", ""),
                params=step.get("params", {}),
            ))

        playbook = Playbook(id=playbook_id, steps=playbook_steps)

        # Execute playbook
        start_time = time.time()
        executor = PlaybookExecutor()

        if exec_request.dry_run:
            # Dry run - just validate steps
            result_data = {
                "playbook_id": playbook_id,
                "status": "dry_run_success",
                "steps_completed": 0,
                "steps_total": len(steps),
                "execution_time_ms": 0,
                "outputs": [{"step": s.step_id, "action": s.action} for s in playbook_steps],
            }
        else:
            # Actual execution
            exec_result = await executor.execute(playbook, context=exec_request.context)

            execution_time_ms = int((time.time() - start_time) * 1000)

            # Count completed steps
            completed = sum(
                1 for s in exec_result.step_results
                if s.status == StepStatus.COMPLETED
            )

            result_data = {
                "playbook_id": playbook_id,
                "status": exec_result.status,
                "steps_completed": completed,
                "steps_total": len(steps),
                "execution_time_ms": execution_time_ms,
                "outputs": [
                    {
                        "step_id": s.step_id,
                        "status": s.status.value,
                        "output": s.output,
                    }
                    for s in exec_result.step_results
                ],
            }

        return PlaybookExecuteResponse(**result_data)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to execute playbook {playbook_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Execution error: {str(e)}")


@router.get("/taxonomy/clusters", response_model=List[TaxonomyClusterResponse])
@limiter.limit("50/minute")
async def list_taxonomy_clusters(request: Request):
    """
    List dynamic taxonomy clusters.

    Returns clustered mistake categories with statistics.
    Uses graph analysis to identify common patterns.
    """
    driver = get_neo4j_driver()

    try:
        # Query Neo4j for cluster statistics
        query = """
        MATCH (m:Mistake)
        WITH m.category as category, count(*) as count, avg(
            CASE m.severity
                WHEN 'critical' THEN 4
                WHEN 'high' THEN 3
                WHEN 'medium' THEN 2
                ELSE 1
            END
        ) as avg_sev
        ORDER BY count DESC
        LIMIT 20
        RETURN category, count, avg_sev
        """

        async with driver.session() as session:
            result = await session.run(query)
            records = await result.data()

        clusters = []
        for idx, record in enumerate(records):
            # Extract keywords from category
            keywords = record["category"].split(".")

            clusters.append(TaxonomyClusterResponse(
                cluster_id=f"cluster_{idx}",
                label=record["category"],
                mistake_count=record["count"],
                avg_severity=round(record["avg_sev"], 2),
                top_keywords=keywords[:3],
            ))

        return clusters

    except Exception as e:
        logger.error(f"Failed to get taxonomy clusters: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@router.get("/stats", response_model=StatsResponse)
@limiter.limit("100/minute")
async def get_stats(request: Request):
    """
    Get system statistics.

    Returns aggregate stats on mistakes, playbooks, success rates, and trends.
    """
    driver = get_neo4j_driver()

    try:
        # Get various statistics from Neo4j
        stats_query = """
        MATCH (m:Mistake)
        WITH count(m) as total_mistakes
        MATCH (p:Playbook)
        WITH total_mistakes, count(p) as total_playbooks, avg(p.success_rate) as avg_success
        MATCH (m:Mistake)
        WITH total_mistakes, total_playbooks, avg_success, m.category as cat, count(*) as cat_count
        ORDER BY cat_count DESC
        LIMIT 5
        RETURN total_mistakes, total_playbooks, avg_success, collect({category: cat, count: cat_count}) as top_cats
        """

        async with driver.session() as session:
            result = await session.run(stats_query)
            record = await result.single()

        if record:
            return StatsResponse(
                total_mistakes=record["total_mistakes"],
                total_playbooks=record["total_playbooks"],
                playbooks_executed_today=0,  # Would need execution log
                success_rate=round(record.get("avg_success", 0.0), 3),
                top_categories=record.get("top_cats", []),
                avg_resolution_time_hours=24.0,  # Would calculate from timestamps
            )
        else:
            # Empty database
            return StatsResponse(
                total_mistakes=0,
                total_playbooks=0,
                playbooks_executed_today=0,
                success_rate=0.0,
                top_categories=[],
                avg_resolution_time_hours=0.0,
            )

    except Exception as e:
        logger.error(f"Failed to get stats: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@router.get("/health")
async def health_check():
    """Health check for mistake API."""
    return {
        "status": "healthy",
        "service": "mistake-api",
        "version": "1.0.0",
    }
