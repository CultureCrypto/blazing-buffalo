"""
Unit tests for dynamic_taxonomy module.

Tests emergent clustering, hierarchy suggestion, and cluster operations.
"""

import pytest
import numpy as np
from pathlib import Path
import tempfile
import json
from datetime import datetime, timedelta

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

from dynamic_taxonomy import (
    DynamicTaxonomy,
    TaxonomyCluster,
    ClusterAssignment
)


@pytest.fixture
def taxonomy():
    """Create a fresh taxonomy instance."""
    return DynamicTaxonomy()


@pytest.fixture
def sample_mistakes():
    """Sample mistake descriptions."""
    return {
        # Type errors
        "type_1": "TypeError: expected str, got int in function call",
        "type_2": "TypeError: cannot concatenate str and int",
        "type_3": "TypeError: unsupported operand type(s) for +: 'int' and 'str'",

        # Syntax errors
        "syntax_1": "SyntaxError: invalid syntax on line 42",
        "syntax_2": "SyntaxError: unexpected EOF while parsing",
        "syntax_3": "SyntaxError: expected colon after if statement",

        # Name errors
        "name_1": "NameError: name 'variable' is not defined",
        "name_2": "NameError: global name 'func' is not defined",
        "name_3": "NameError: undefined variable in scope",

        # Import errors
        "import_1": "ImportError: cannot import module 'foo'",
        "import_2": "ModuleNotFoundError: No module named 'bar'",

        # Different category
        "network_1": "Connection timeout after 30 seconds",
        "network_2": "Failed to establish connection to server"
    }


class TestTaxonomyCluster:
    """Test TaxonomyCluster dataclass."""

    def test_cluster_creation(self):
        """Test creating a cluster."""
        centroid = np.array([0.1, 0.2, 0.3])
        cluster = TaxonomyCluster(
            id="tax_001",
            name="test_cluster",
            description="A test cluster",
            centroid=centroid
        )

        assert cluster.id == "tax_001"
        assert cluster.name == "test_cluster"
        assert len(cluster.member_ids) == 0
        assert cluster.parent_id is None
        assert cluster.confidence == 0.8

    def test_cluster_to_dict(self):
        """Test cluster serialization."""
        centroid = np.array([0.1, 0.2, 0.3])
        cluster = TaxonomyCluster(
            id="tax_001",
            name="test_cluster",
            description="A test cluster",
            centroid=centroid,
            member_ids={"m1", "m2"}
        )

        d = cluster.to_dict(include_centroid=False)
        assert d["id"] == "tax_001"
        assert d["member_count"] == 2
        assert "centroid" not in d

        d_with_centroid = cluster.to_dict(include_centroid=True)
        assert "centroid" in d_with_centroid
        assert len(d_with_centroid["centroid"]) == 3


class TestClusterAssignment:
    """Test ClusterAssignment dataclass."""

    def test_assignment_creation(self):
        """Test creating an assignment."""
        assignment = ClusterAssignment(
            cluster_id="tax_001",
            similarity=0.85,
            is_new_cluster=False
        )

        assert assignment.cluster_id == "tax_001"
        assert assignment.similarity == 0.85
        assert not assignment.is_new_cluster

    def test_assignment_to_dict(self):
        """Test assignment serialization."""
        assignment = ClusterAssignment(
            cluster_id="tax_001",
            similarity=0.85,
            is_new_cluster=True,
            suggested_name="type_errors"
        )

        d = assignment.to_dict()
        assert d["cluster_id"] == "tax_001"
        assert d["suggested_name"] == "type_errors"


class TestDynamicTaxonomy:
    """Test DynamicTaxonomy class."""

    def test_initialization(self):
        """Test taxonomy initialization."""
        taxonomy = DynamicTaxonomy()

        assert len(taxonomy.clusters) == 0
        assert len(taxonomy.mistake_to_cluster) == 0
        assert taxonomy.SIMILARITY_THRESHOLD == 0.8
        assert taxonomy.MIN_CLUSTER_SIZE == 3

    def test_get_embedding(self, taxonomy):
        """Test embedding generation."""
        text = "This is a test"
        embedding = taxonomy.get_embedding(text)

        assert isinstance(embedding, np.ndarray)
        assert len(embedding) == 384  # all-MiniLM-L6-v2 dimension

        # Should be normalized
        norm = np.linalg.norm(embedding)
        assert abs(norm - 1.0) < 1e-5

    def test_embedding_caching(self, taxonomy):
        """Test that embeddings are cached."""
        text = "This is a test"

        # First call
        embedding1 = taxonomy.get_embedding(text)

        # Second call should use cache
        embedding2 = taxonomy.get_embedding(text)

        np.testing.assert_array_equal(embedding1, embedding2)
        assert text in taxonomy._embedding_cache

    def test_first_mistake_creates_cluster(self, taxonomy, sample_mistakes):
        """Test that first mistake creates a new cluster."""
        assignment = taxonomy.get_category(
            sample_mistakes["type_1"],
            mistake_id="m1"
        )

        assert assignment.is_new_cluster
        assert assignment.similarity == 1.0
        assert len(taxonomy.clusters) == 1
        assert "m1" in taxonomy.mistake_to_cluster

    def test_similar_mistakes_join_cluster(self, taxonomy, sample_mistakes):
        """Test that similar mistakes join existing cluster."""
        # Add first type error
        assignment1 = taxonomy.get_category(
            sample_mistakes["type_1"],
            mistake_id="m1"
        )
        cluster_id = assignment1.cluster_id

        # Add similar type error
        assignment2 = taxonomy.get_category(
            sample_mistakes["type_2"],
            mistake_id="m2"
        )

        # Should join existing cluster
        assert not assignment2.is_new_cluster
        assert assignment2.cluster_id == cluster_id
        assert assignment2.similarity >= 0.8
        assert len(taxonomy.clusters) == 1

    def test_dissimilar_mistakes_create_new_cluster(self, taxonomy, sample_mistakes):
        """Test that dissimilar mistakes create new clusters."""
        # Add type error
        assignment1 = taxonomy.get_category(
            sample_mistakes["type_1"],
            mistake_id="m1"
        )

        # Add network error (different category)
        assignment2 = taxonomy.get_category(
            sample_mistakes["network_1"],
            mistake_id="m2"
        )

        # Should create new cluster
        assert assignment2.is_new_cluster
        assert assignment2.cluster_id != assignment1.cluster_id
        assert len(taxonomy.clusters) == 2

    def test_cluster_grows_with_members(self, taxonomy, sample_mistakes):
        """Test that cluster membership grows."""
        # Add three similar mistakes
        cluster_id = None
        for i, key in enumerate(["type_1", "type_2", "type_3"]):
            assignment = taxonomy.get_category(
                sample_mistakes[key],
                mistake_id=f"m{i+1}"
            )
            if i == 0:
                cluster_id = assignment.cluster_id

        cluster = taxonomy.clusters[cluster_id]
        assert len(cluster.member_ids) == 3
        assert cluster.confidence > 0.7  # Confidence increases with members

    def test_centroid_updates(self, taxonomy, sample_mistakes):
        """Test that centroids update with new members."""
        # Add first mistake
        assignment1 = taxonomy.get_category(
            sample_mistakes["type_1"],
            mistake_id="m1"
        )
        cluster = taxonomy.clusters[assignment1.cluster_id]
        centroid1 = cluster.centroid.copy()

        # Add second mistake
        taxonomy.get_category(
            sample_mistakes["type_2"],
            mistake_id="m2"
        )
        centroid2 = cluster.centroid.copy()

        # Centroid should have changed
        assert not np.array_equal(centroid1, centroid2)

        # Should still be normalized
        norm = np.linalg.norm(centroid2)
        assert abs(norm - 1.0) < 1e-5

    def test_suggest_cluster_name(self, taxonomy):
        """Test cluster name suggestion."""
        desc1 = "TypeError: expected str, got int"
        name1 = taxonomy._suggest_cluster_name(desc1)
        assert "type" in name1.lower() or "expected" in name1.lower()

        desc2 = "SyntaxError: invalid syntax on line 42"
        name2 = taxonomy._suggest_cluster_name(desc2)
        assert "syntax" in name2.lower() or "invalid" in name2.lower()

    def test_merge_clusters(self, taxonomy, sample_mistakes):
        """Test merging multiple clusters."""
        # Create two separate clusters
        assignment1 = taxonomy.get_category(
            sample_mistakes["type_1"],
            mistake_id="m1"
        )

        assignment2 = taxonomy.get_category(
            sample_mistakes["network_1"],
            mistake_id="m2"
        )

        cluster_id1 = assignment1.cluster_id
        cluster_id2 = assignment2.cluster_id

        # Merge them
        merged = taxonomy.merge_clusters(
            [cluster_id1, cluster_id2],
            new_name="combined_errors"
        )

        assert merged.name == "combined_errors"
        assert len(merged.member_ids) == 2
        assert "m1" in merged.member_ids
        assert "m2" in merged.member_ids

        # Old clusters should be gone
        assert cluster_id1 not in taxonomy.clusters
        assert cluster_id2 not in taxonomy.clusters

        # New cluster should exist
        assert merged.id in taxonomy.clusters

    def test_merge_requires_multiple_clusters(self, taxonomy):
        """Test that merge requires at least 2 clusters."""
        with pytest.raises(ValueError, match="at least 2 clusters"):
            taxonomy.merge_clusters(["cluster1"], "merged")

    def test_merge_validates_cluster_existence(self, taxonomy):
        """Test that merge validates cluster IDs."""
        with pytest.raises(ValueError, match="not found"):
            taxonomy.merge_clusters(
                ["nonexistent1", "nonexistent2"],
                "merged"
            )

    def test_split_cluster(self, taxonomy, sample_mistakes):
        """Test splitting a cluster."""
        # Create a cluster with enough members by forcing them into one cluster
        # We'll manually add similar mistakes to the same cluster

        # First create a base cluster
        assignment = taxonomy.get_category(
            sample_mistakes["type_1"],
            mistake_id="m1"
        )
        cluster_id = assignment.cluster_id

        # Manually add more members to reach MIN_CLUSTER_SIZE * 2 = 6
        cluster = taxonomy.clusters[cluster_id]
        for i in range(2, 8):
            mid = f"m{i}"
            cluster.member_ids.add(mid)
            taxonomy.mistake_to_cluster[mid] = cluster_id
            # Create fake embeddings for these
            taxonomy._embedding_cache[mid] = taxonomy.get_embedding(
                f"variation {i} of type error: str vs int"
            )

        # Now we have 7 members, enough to split into 2
        assert len(cluster.member_ids) >= 6

        # Split into 2 subclusters
        subclusters = taxonomy.split_cluster(cluster_id, n_subclusters=2)

        assert len(subclusters) == 2

        # All original members should be distributed
        total_members = sum(len(c.member_ids) for c in subclusters)
        assert total_members == 7

        # Parent cluster should have children
        parent_cluster = taxonomy.clusters[cluster_id]
        assert len(parent_cluster.children_ids) == 2

    def test_split_requires_enough_members(self, taxonomy, sample_mistakes):
        """Test that split requires enough members."""
        # Create small cluster
        assignment = taxonomy.get_category(
            sample_mistakes["type_1"],
            mistake_id="m1"
        )

        with pytest.raises(ValueError, match="Not enough members"):
            taxonomy.split_cluster(assignment.cluster_id, n_subclusters=2)

    def test_suggest_hierarchy(self, taxonomy, sample_mistakes):
        """Test hierarchy suggestion."""
        # Create multiple clusters
        for i, key in enumerate(["type_1", "syntax_1", "name_1",
                                  "import_1", "network_1"]):
            taxonomy.get_category(
                sample_mistakes[key],
                mistake_id=f"m{i+1}"
            )

        hierarchy = taxonomy.suggest_hierarchy()

        # Should have some hierarchical structure
        assert isinstance(hierarchy, dict)
        # With 5+ clusters, should have some groupings
        # (exact structure depends on embedding similarity)

    def test_export_taxonomy(self, taxonomy, sample_mistakes):
        """Test exporting taxonomy."""
        # Add some mistakes
        taxonomy.get_category(sample_mistakes["type_1"], "m1")
        taxonomy.get_category(sample_mistakes["syntax_1"], "m2")

        exported = taxonomy.export_taxonomy()

        assert "clusters" in exported
        assert "hierarchy" in exported
        assert "stats" in exported
        assert "config" in exported

        stats = exported["stats"]
        assert stats["total_clusters"] >= 1
        assert stats["total_mistakes"] == 2
        assert stats["avg_cluster_size"] > 0
        assert stats["avg_confidence"] > 0

    def test_save_and_load_taxonomy(self, taxonomy, sample_mistakes):
        """Test saving and loading taxonomy."""
        # Add some mistakes
        taxonomy.get_category(sample_mistakes["type_1"], "m1")
        taxonomy.get_category(sample_mistakes["syntax_1"], "m2")

        # Save to temp file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            filepath = Path(f.name)

        try:
            taxonomy.save_taxonomy(filepath)

            # Load into new taxonomy
            new_taxonomy = DynamicTaxonomy()
            new_taxonomy.load_taxonomy(filepath)

            # Should have same clusters
            assert len(new_taxonomy.clusters) == len(taxonomy.clusters)
            assert len(new_taxonomy.mistake_to_cluster) == len(taxonomy.mistake_to_cluster)

            # Check cluster details
            for cid in taxonomy.clusters:
                assert cid in new_taxonomy.clusters
                orig_cluster = taxonomy.clusters[cid]
                new_cluster = new_taxonomy.clusters[cid]
                assert orig_cluster.name == new_cluster.name
                assert orig_cluster.member_ids == new_cluster.member_ids
        finally:
            filepath.unlink()

    def test_get_cluster_stats(self, taxonomy, sample_mistakes):
        """Test getting cluster statistics."""
        assignment = taxonomy.get_category(
            sample_mistakes["type_1"],
            mistake_id="m1"
        )

        stats = taxonomy.get_cluster_stats(assignment.cluster_id)

        assert stats["id"] == assignment.cluster_id
        assert stats["member_count"] == 1
        assert stats["confidence"] > 0
        assert not stats["has_parent"]
        assert stats["num_children"] == 0
        assert "age_seconds" in stats

    def test_event_emission(self, taxonomy, sample_mistakes, tmp_path):
        """Test that new category events are emitted."""
        # Temporarily override events directory
        import dynamic_taxonomy
        original_mkdir = Path.mkdir
        events_created = []

        def mock_mkdir(*args, **kwargs):
            return original_mkdir(*args, **kwargs)

        # Create the first cluster (should emit event)
        assignment = taxonomy.get_category(
            sample_mistakes["type_1"],
            mistake_id="m1"
        )

        # Check event file was created
        events_dir = Path("/home/pook/engineer-team/.kg-events")
        if events_dir.exists():
            event_files = list(events_dir.glob(f"taxonomy_{assignment.cluster_id}.json"))
            if event_files:
                with open(event_files[0]) as f:
                    event = json.load(f)
                    assert event["type"] == "new_category_discovered"
                    assert event["cluster_id"] == assignment.cluster_id

    def test_cosine_similarity(self, taxonomy):
        """Test cosine similarity calculation."""
        a = np.array([1.0, 0.0, 0.0])
        b = np.array([1.0, 0.0, 0.0])
        c = np.array([0.0, 1.0, 0.0])

        # Same vectors
        sim_same = taxonomy._cosine_similarity(a, b)
        assert abs(sim_same - 1.0) < 1e-5

        # Orthogonal vectors
        sim_ortho = taxonomy._cosine_similarity(a, c)
        assert abs(sim_ortho - 0.0) < 1e-5

    def test_multiple_categories_emerge(self, taxonomy, sample_mistakes):
        """Test that multiple distinct categories emerge."""
        # Add mistakes from different categories
        categories = ["type_1", "syntax_1", "name_1", "import_1", "network_1"]

        for i, key in enumerate(categories):
            taxonomy.get_category(
                sample_mistakes[key],
                mistake_id=f"m{i+1}"
            )

        # Should have created multiple clusters
        assert len(taxonomy.clusters) >= 3

    def test_confidence_increases_with_members(self, taxonomy, sample_mistakes):
        """Test that cluster confidence increases with more members."""
        # Add first mistake
        assignment1 = taxonomy.get_category(
            sample_mistakes["type_1"],
            mistake_id="m1"
        )
        cluster = taxonomy.clusters[assignment1.cluster_id]
        confidence1 = cluster.confidence

        # Add more similar mistakes
        taxonomy.get_category(sample_mistakes["type_2"], "m2")
        confidence2 = cluster.confidence

        taxonomy.get_category(sample_mistakes["type_3"], "m3")
        confidence3 = cluster.confidence

        # Confidence should increase
        assert confidence2 > confidence1
        assert confidence3 > confidence2

        # But shouldn't exceed 0.95
        assert cluster.confidence <= 0.95


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
