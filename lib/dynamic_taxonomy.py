"""
Dynamic Taxonomy with Emergent Clustering

Self-organizing mistake taxonomy that discovers categories through
semantic clustering rather than rigid predefined hierarchies.

Key Features:
- No rigid categories - patterns emerge from data
- Embedding-based clustering using all-MiniLM-L6-v2
- Automatic hierarchy suggestion
- Merge/split operations
- Event emission for new category discovery
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set, Tuple
from datetime import datetime
import numpy as np
from collections import defaultdict
import json
from pathlib import Path


@dataclass
class TaxonomyCluster:
    """A dynamically discovered category cluster."""
    id: str
    name: str  # Auto-generated or human-assigned
    description: str
    centroid: np.ndarray  # Cluster center embedding
    member_ids: Set[str] = field(default_factory=set)
    parent_id: Optional[str] = None
    children_ids: Set[str] = field(default_factory=set)
    created_at: datetime = field(default_factory=datetime.utcnow)
    confidence: float = 0.8  # How well-defined is this cluster
    metadata: Dict = field(default_factory=dict)

    def to_dict(self, include_centroid: bool = False) -> Dict:
        """Convert to serializable dict."""
        result = {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "member_count": len(self.member_ids),
            "member_ids": list(self.member_ids),
            "parent_id": self.parent_id,
            "children_ids": list(self.children_ids),
            "created_at": self.created_at.isoformat(),
            "confidence": self.confidence,
            "metadata": self.metadata
        }
        if include_centroid:
            result["centroid"] = self.centroid.tolist()
        return result


@dataclass
class ClusterAssignment:
    """Result of assigning a mistake to a cluster."""
    cluster_id: str
    similarity: float
    is_new_cluster: bool
    suggested_name: Optional[str] = None

    def to_dict(self) -> Dict:
        """Convert to serializable dict."""
        return {
            "cluster_id": self.cluster_id,
            "similarity": self.similarity,
            "is_new_cluster": self.is_new_cluster,
            "suggested_name": self.suggested_name
        }


class DynamicTaxonomy:
    """
    Self-organizing taxonomy that discovers mistake categories
    through embedding-based semantic clustering.

    Usage:
        taxonomy = DynamicTaxonomy()
        assignment = taxonomy.get_category(
            "TypeError: expected str, got int",
            mistake_id="m_001"
        )

        hierarchy = taxonomy.suggest_hierarchy()
        exported = taxonomy.export_taxonomy()
    """

    SIMILARITY_THRESHOLD = 0.8  # Threshold for cluster membership
    MIN_CLUSTER_SIZE = 3  # Minimum mistakes to form a cluster
    MAX_DEPTH = 4  # Maximum hierarchy depth

    def __init__(self, embedding_model: str = "all-MiniLM-L6-v2"):
        """
        Initialize taxonomy.

        Args:
            embedding_model: Sentence transformer model name
        """
        self.embedding_model = embedding_model
        self.clusters: Dict[str, TaxonomyCluster] = {}
        self.mistake_to_cluster: Dict[str, str] = {}
        self._embedder = None
        self._embedding_cache: Dict[str, np.ndarray] = {}

    @property
    def embedder(self):
        """Lazy load the embedding model."""
        if self._embedder is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._embedder = SentenceTransformer(self.embedding_model)
            except ImportError:
                raise ImportError(
                    "sentence-transformers required: "
                    "pip install sentence-transformers"
                )
        return self._embedder

    def get_embedding(self, text: str) -> np.ndarray:
        """
        Generate embedding for text.

        Args:
            text: Text to embed

        Returns:
            Normalized embedding vector
        """
        # Check cache first
        if text in self._embedding_cache:
            return self._embedding_cache[text]

        embedding = self.embedder.encode(text, normalize_embeddings=True)
        self._embedding_cache[text] = embedding
        return embedding

    def get_category(self, mistake_description: str,
                     mistake_id: str) -> ClusterAssignment:
        """
        Find or create the best category for a mistake.

        Args:
            mistake_description: Text description of the mistake
            mistake_id: Unique ID of the mistake

        Returns:
            ClusterAssignment with cluster info and similarity score
        """
        embedding = self.get_embedding(mistake_description)

        # Find best matching cluster
        best_cluster = None
        best_similarity = 0.0

        for cluster in self.clusters.values():
            similarity = self._cosine_similarity(embedding, cluster.centroid)
            if similarity > best_similarity:
                best_similarity = similarity
                best_cluster = cluster

        # Check if similarity meets threshold
        if best_cluster and best_similarity >= self.SIMILARITY_THRESHOLD:
            # Add to existing cluster
            best_cluster.member_ids.add(mistake_id)
            self.mistake_to_cluster[mistake_id] = best_cluster.id
            self._update_centroid(best_cluster, embedding)

            # Cache the embedding for this mistake
            self._embedding_cache[mistake_id] = embedding

            return ClusterAssignment(
                cluster_id=best_cluster.id,
                similarity=best_similarity,
                is_new_cluster=False
            )
        else:
            # Create new cluster
            new_cluster = self._create_cluster(
                embedding=embedding,
                mistake_id=mistake_id,
                description=mistake_description
            )

            # Cache the embedding for this mistake
            self._embedding_cache[mistake_id] = embedding

            # Emit event for new category discovery
            self._emit_new_category_event(new_cluster)

            return ClusterAssignment(
                cluster_id=new_cluster.id,
                similarity=1.0,
                is_new_cluster=True,
                suggested_name=self._suggest_cluster_name(mistake_description)
            )

    def suggest_hierarchy(self) -> Dict[str, List[str]]:
        """
        Use hierarchical clustering to suggest a taxonomy structure.

        Returns:
            Dict mapping parent cluster IDs to child cluster IDs
        """
        if len(self.clusters) < 2:
            return {}

        try:
            from scipy.cluster.hierarchy import linkage, fcluster
        except ImportError:
            raise ImportError("scipy required: pip install scipy")

        # Collect all centroids
        cluster_ids = list(self.clusters.keys())
        centroids = np.array([
            self.clusters[cid].centroid for cid in cluster_ids
        ])

        # Hierarchical clustering using average linkage
        Z = linkage(centroids, method='average', metric='cosine')

        # Cut at various levels to get hierarchy
        hierarchy = {}
        for depth in range(1, self.MAX_DEPTH + 1):
            threshold = 1.0 - (depth * 0.15)  # Adjust threshold per level
            labels = fcluster(Z, t=threshold, criterion='distance')

            # Group clusters by their parent
            parent_groups = defaultdict(list)
            for idx, label in enumerate(labels):
                parent_id = f"parent_{depth}_{label}"
                parent_groups[parent_id].append(cluster_ids[idx])

            # Only keep groups with multiple children
            for parent_id, children in parent_groups.items():
                if len(children) > 1:
                    hierarchy[parent_id] = children

        return hierarchy

    def merge_clusters(self, cluster_ids: List[str],
                       new_name: str,
                       new_description: Optional[str] = None) -> TaxonomyCluster:
        """
        Merge multiple clusters into one.

        Args:
            cluster_ids: IDs of clusters to merge
            new_name: Name for the merged cluster
            new_description: Optional description (auto-generated if None)

        Returns:
            The new merged cluster
        """
        if not cluster_ids:
            raise ValueError("No clusters to merge")

        if len(cluster_ids) < 2:
            raise ValueError("Need at least 2 clusters to merge")

        # Validate all clusters exist
        for cid in cluster_ids:
            if cid not in self.clusters:
                raise ValueError(f"Cluster {cid} not found")

        # Collect all member IDs and compute new centroid
        all_members = set()
        centroids = []

        for cid in cluster_ids:
            cluster = self.clusters[cid]
            all_members.update(cluster.member_ids)
            centroids.append(cluster.centroid)

        # Compute mean centroid
        new_centroid = np.mean(centroids, axis=0)
        new_centroid = new_centroid / np.linalg.norm(new_centroid)

        # Create merged cluster
        import uuid
        merged = TaxonomyCluster(
            id=f"tax_{uuid.uuid4().hex[:8]}",
            name=new_name,
            description=(
                new_description or
                f"Merged from {len(cluster_ids)} clusters"
            ),
            centroid=new_centroid,
            member_ids=all_members,
            confidence=0.9,
            metadata={
                "merged_from": cluster_ids,
                "merge_timestamp": datetime.utcnow().isoformat()
            }
        )

        # Remove old clusters
        for cid in cluster_ids:
            del self.clusters[cid]

        # Add merged cluster
        self.clusters[merged.id] = merged

        # Update mistake mappings
        for mid in all_members:
            self.mistake_to_cluster[mid] = merged.id

        return merged

    def split_cluster(self, cluster_id: str,
                      n_subclusters: int = 2) -> List[TaxonomyCluster]:
        """
        Split a cluster into subclusters using k-means.

        Args:
            cluster_id: ID of cluster to split
            n_subclusters: Number of subclusters to create

        Returns:
            List of new subclusters
        """
        if cluster_id not in self.clusters:
            raise ValueError(f"Cluster {cluster_id} not found")

        cluster = self.clusters[cluster_id]

        if len(cluster.member_ids) < n_subclusters * self.MIN_CLUSTER_SIZE:
            raise ValueError(
                f"Not enough members to split. Need at least "
                f"{n_subclusters * self.MIN_CLUSTER_SIZE}, "
                f"have {len(cluster.member_ids)}"
            )

        try:
            from sklearn.cluster import KMeans
        except ImportError:
            raise ImportError("scikit-learn required: pip install scikit-learn")

        # Get embeddings for all members
        member_embeddings = []
        member_ids_list = list(cluster.member_ids)

        for mid in member_ids_list:
            if mid in self._embedding_cache:
                member_embeddings.append(self._embedding_cache[mid])
            else:
                # This shouldn't happen if get_category was used
                raise ValueError(f"No cached embedding for {mid}")

        embeddings_matrix = np.array(member_embeddings)

        # Run k-means
        kmeans = KMeans(n_clusters=n_subclusters, random_state=42)
        labels = kmeans.fit_predict(embeddings_matrix)

        # Create new subclusters
        import uuid
        new_clusters = []

        for i in range(n_subclusters):
            # Get members for this subcluster
            subcluster_members = {
                member_ids_list[idx]
                for idx, label in enumerate(labels)
                if label == i
            }

            # Skip empty clusters
            if not subcluster_members:
                continue

            # Create subcluster
            subcluster = TaxonomyCluster(
                id=f"tax_{uuid.uuid4().hex[:8]}",
                name=f"{cluster.name}_split_{i+1}",
                description=f"Split from {cluster.id}",
                centroid=kmeans.cluster_centers_[i] / np.linalg.norm(kmeans.cluster_centers_[i]),
                member_ids=subcluster_members,
                parent_id=cluster_id,
                confidence=0.75,
                metadata={
                    "split_from": cluster_id,
                    "split_timestamp": datetime.utcnow().isoformat()
                }
            )

            new_clusters.append(subcluster)
            self.clusters[subcluster.id] = subcluster

            # Update cluster's children
            cluster.children_ids.add(subcluster.id)

            # Update mistake mappings
            for mid in subcluster_members:
                self.mistake_to_cluster[mid] = subcluster.id

        return new_clusters

    def _create_cluster(self, embedding: np.ndarray,
                        mistake_id: str,
                        description: str) -> TaxonomyCluster:
        """Create a new cluster for a mistake."""
        import uuid

        cluster = TaxonomyCluster(
            id=f"tax_{uuid.uuid4().hex[:8]}",
            name=self._suggest_cluster_name(description),
            description=description[:200],
            centroid=embedding.copy(),
            member_ids={mistake_id},
            confidence=0.7  # New clusters start with lower confidence
        )

        self.clusters[cluster.id] = cluster
        self.mistake_to_cluster[mistake_id] = cluster.id

        return cluster

    def _update_centroid(self, cluster: TaxonomyCluster,
                         new_embedding: np.ndarray) -> None:
        """Update cluster centroid with new member (running average)."""
        n = len(cluster.member_ids)
        cluster.centroid = (
            (cluster.centroid * (n - 1) + new_embedding) / n
        )
        # Normalize
        cluster.centroid = cluster.centroid / np.linalg.norm(cluster.centroid)

        # Increase confidence with more members
        cluster.confidence = min(0.95, 0.7 + (n * 0.02))

    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """Compute cosine similarity between two vectors."""
        return float(np.dot(a, b))

    def _suggest_cluster_name(self, description: str) -> str:
        """Generate a suggested name for a cluster based on description."""
        import re

        # Remove common words
        stopwords = {
            'the', 'a', 'an', 'is', 'was', 'were', 'be', 'been',
            'being', 'have', 'has', 'had', 'do', 'does', 'did',
            'will', 'would', 'could', 'should', 'may', 'might',
            'must', 'shall', 'can', 'need', 'to', 'of', 'in',
            'for', 'on', 'with', 'at', 'by', 'from', 'as', 'into',
            'through', 'during', 'before', 'after', 'above', 'below',
            'between', 'under', 'again', 'further', 'then', 'once',
            'here', 'there', 'when', 'where', 'why', 'how', 'all',
            'each', 'few', 'more', 'most', 'other', 'some', 'such',
            'no', 'nor', 'not', 'only', 'own', 'same', 'so', 'than',
            'too', 'very', 'just', 'and', 'but', 'if', 'or', 'because',
            'this', 'that', 'these', 'those', 'it', 'its'
        }

        words = re.findall(r'\b[a-z]+\b', description.lower())
        keywords = [w for w in words if w not in stopwords and len(w) > 2]

        # Take top 3 keywords
        from collections import Counter
        top_keywords = [w for w, _ in Counter(keywords).most_common(3)]

        if top_keywords:
            return '_'.join(top_keywords)
        return "unnamed_cluster"

    def _emit_new_category_event(self, cluster: TaxonomyCluster) -> None:
        """Emit event when new category is discovered."""
        event = {
            "type": "new_category_discovered",
            "cluster_id": cluster.id,
            "cluster_name": cluster.name,
            "timestamp": datetime.utcnow().isoformat(),
            "confidence": cluster.confidence,
            "description": cluster.description
        }

        # Write to events directory
        events_dir = Path("/home/pook/engineer-team/.kg-events")
        events_dir.mkdir(exist_ok=True)

        event_file = events_dir / f"taxonomy_{cluster.id}.json"
        with open(event_file, 'w') as f:
            json.dump(event, f, indent=2)

    def export_taxonomy(self) -> Dict:
        """Export taxonomy as serializable dict."""
        return {
            "clusters": {
                cid: c.to_dict(include_centroid=False)
                for cid, c in self.clusters.items()
            },
            "hierarchy": self.suggest_hierarchy(),
            "stats": {
                "total_clusters": len(self.clusters),
                "total_mistakes": len(self.mistake_to_cluster),
                "avg_cluster_size": (
                    sum(len(c.member_ids) for c in self.clusters.values())
                    / max(1, len(self.clusters))
                ),
                "avg_confidence": (
                    sum(c.confidence for c in self.clusters.values())
                    / max(1, len(self.clusters))
                )
            },
            "config": {
                "similarity_threshold": self.SIMILARITY_THRESHOLD,
                "min_cluster_size": self.MIN_CLUSTER_SIZE,
                "max_depth": self.MAX_DEPTH,
                "embedding_model": self.embedding_model
            }
        }

    def save_taxonomy(self, filepath: Path) -> None:
        """
        Save taxonomy to file.

        Args:
            filepath: Path to save taxonomy JSON
        """
        taxonomy_data = self.export_taxonomy()

        # Add centroids for persistence
        taxonomy_data["centroids"] = {
            cid: cluster.centroid.tolist()
            for cid, cluster in self.clusters.items()
        }

        with open(filepath, 'w') as f:
            json.dump(taxonomy_data, f, indent=2)

    def load_taxonomy(self, filepath: Path) -> None:
        """
        Load taxonomy from file.

        Args:
            filepath: Path to taxonomy JSON file
        """
        with open(filepath, 'r') as f:
            data = json.load(f)

        # Clear existing clusters
        self.clusters.clear()
        self.mistake_to_cluster.clear()

        # Restore clusters
        centroids = data.get("centroids", {})
        for cid, cluster_data in data.get("clusters", {}).items():
            cluster = TaxonomyCluster(
                id=cluster_data["id"],
                name=cluster_data["name"],
                description=cluster_data["description"],
                centroid=np.array(centroids[cid]),
                member_ids=set(cluster_data["member_ids"]),
                parent_id=cluster_data.get("parent_id"),
                children_ids=set(cluster_data.get("children_ids", [])),
                created_at=datetime.fromisoformat(cluster_data["created_at"]),
                confidence=cluster_data["confidence"],
                metadata=cluster_data.get("metadata", {})
            )
            self.clusters[cid] = cluster

            # Restore mistake mappings
            for mid in cluster.member_ids:
                self.mistake_to_cluster[mid] = cid

    def get_cluster_stats(self, cluster_id: str) -> Dict:
        """
        Get statistics for a specific cluster.

        Args:
            cluster_id: Cluster ID

        Returns:
            Dict with cluster statistics
        """
        if cluster_id not in self.clusters:
            raise ValueError(f"Cluster {cluster_id} not found")

        cluster = self.clusters[cluster_id]

        return {
            "id": cluster.id,
            "name": cluster.name,
            "member_count": len(cluster.member_ids),
            "confidence": cluster.confidence,
            "has_parent": cluster.parent_id is not None,
            "num_children": len(cluster.children_ids),
            "created_at": cluster.created_at.isoformat(),
            "age_seconds": (datetime.utcnow() - cluster.created_at).total_seconds()
        }
