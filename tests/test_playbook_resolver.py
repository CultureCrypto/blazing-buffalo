"""
Tests for Playbook Resolver (BB-017).

Tests cover:
- Three-layer playbook resolution (global → project-type → local)
- Deep merge configuration override
- Inheritance chain tracking
- Project type auto-detection
- "extends" syntax for playbook inheritance
- List available playbooks
- Cache management
- Error handling
- Export functionality
"""

import pytest
from pathlib import Path
from tempfile import TemporaryDirectory
import yaml
from copy import deepcopy

from lib.playbook_resolver import PlaybookResolver, ResolvedPlaybook


@pytest.fixture
def temp_playbook_dirs():
    """Create temporary playbook directory structure."""
    with TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)

        # Create directory structure
        global_dir = base / "global"
        python_dir = base / "python"
        typescript_dir = base / "typescript"
        go_dir = base / "go"
        local_dir = base / "project" / ".playbooks"

        for d in [global_dir, python_dir, typescript_dir, go_dir, local_dir]:
            d.mkdir(parents=True, exist_ok=True)

        # Temporarily patch PlaybookResolver
        original_global = PlaybookResolver.GLOBAL_DIR
        original_type = PlaybookResolver.PROJECT_TYPE_DIR

        PlaybookResolver.GLOBAL_DIR = global_dir
        PlaybookResolver.PROJECT_TYPE_DIR = base

        yield {
            "base": base,
            "global": global_dir,
            "python": python_dir,
            "typescript": typescript_dir,
            "go": go_dir,
            "local": local_dir,
            "project_root": base / "project",
        }

        # Restore
        PlaybookResolver.GLOBAL_DIR = original_global
        PlaybookResolver.PROJECT_TYPE_DIR = original_type


def create_playbook(path: Path, playbook_id: str, config: dict) -> None:
    """Helper to create a playbook file."""
    config_with_id = {"id": playbook_id, **config}
    path.mkdir(parents=True, exist_ok=True)
    with open(path / f"{playbook_id}.yaml", "w") as f:
        yaml.dump(config_with_id, f)


class TestBasicResolution:
    """Test basic three-layer resolution."""

    def test_resolve_global_only(self, temp_playbook_dirs):
        """Test resolving playbook from global layer only."""
        dirs = temp_playbook_dirs
        create_playbook(
            dirs["global"],
            "type-error-fix",
            {"trigger": {"patterns": ["TypeError"]}, "timeout": "fast"},
        )

        resolver = PlaybookResolver(
            project_root=dirs["project_root"],
            project_type="python",
        )
        resolved = resolver.resolve("type-error-fix")

        assert resolved.id == "type-error-fix"
        assert "global" in resolved.layers_applied
        assert resolved.final_config["trigger"]["patterns"] == ["TypeError"]
        assert resolved.final_config["timeout"] == "fast"

    def test_resolve_global_and_type(self, temp_playbook_dirs):
        """Test resolution with both global and project-type layers."""
        dirs = temp_playbook_dirs
        create_playbook(
            dirs["global"],
            "type-error-fix",
            {
                "trigger": {"patterns": ["TypeError"]},
                "timeout": "fast",
                "severity": "medium",
            },
        )
        create_playbook(
            dirs["python"],
            "type-error-fix",
            {
                "trigger": {"patterns": ["TypeError", "pyright"]},
                "severity": "high",
            },
        )

        resolver = PlaybookResolver(
            project_root=dirs["project_root"],
            project_type="python",
        )
        resolved = resolver.resolve("type-error-fix")

        # Project-type overrides global
        assert "global" in resolved.layers_applied
        assert "project-type:python" in resolved.layers_applied
        assert resolved.final_config["trigger"]["patterns"] == ["TypeError", "pyright"]
        assert resolved.final_config["severity"] == "high"
        assert resolved.final_config["timeout"] == "fast"  # From global

    def test_resolve_all_three_layers(self, temp_playbook_dirs):
        """Test resolution with all three layers."""
        dirs = temp_playbook_dirs
        create_playbook(
            dirs["global"],
            "type-error-fix",
            {
                "trigger": {"patterns": ["TypeError"]},
                "timeout": "fast",
                "min_confidence": 0.7,
            },
        )
        create_playbook(
            dirs["python"],
            "type-error-fix",
            {
                "trigger": {"patterns": ["TypeError", "pyright"]},
                "min_confidence": 0.8,
            },
        )
        create_playbook(
            dirs["local"],
            "type-error-fix",
            {"min_confidence": 0.9, "max_retries": 3},
        )

        resolver = PlaybookResolver(
            project_root=dirs["project_root"],
            project_type="python",
        )
        resolved = resolver.resolve("type-error-fix")

        assert "global" in resolved.layers_applied
        assert "project-type:python" in resolved.layers_applied
        assert "local" in resolved.layers_applied
        assert resolved.final_config["min_confidence"] == 0.9  # From local
        assert resolved.final_config["timeout"] == "fast"  # From global
        assert resolved.final_config["max_retries"] == 3  # From local

    def test_resolve_local_only(self, temp_playbook_dirs):
        """Test resolving playbook from local layer only."""
        dirs = temp_playbook_dirs
        create_playbook(
            dirs["local"],
            "custom-playbook",
            {"custom_field": "value", "enabled": True},
        )

        resolver = PlaybookResolver(
            project_root=dirs["project_root"],
            project_type="python",
        )
        resolved = resolver.resolve("custom-playbook")

        assert "local" in resolved.layers_applied
        assert resolved.final_config["custom_field"] == "value"

    def test_resolve_not_found(self, temp_playbook_dirs):
        """Test error when playbook not found."""
        dirs = temp_playbook_dirs
        resolver = PlaybookResolver(
            project_root=dirs["project_root"],
            project_type="python",
        )

        with pytest.raises(FileNotFoundError):
            resolver.resolve("nonexistent")


class TestDeepMerge:
    """Test deep merge behavior."""

    def test_merge_scalars(self, temp_playbook_dirs):
        """Test that scalars are replaced, not merged."""
        dirs = temp_playbook_dirs
        create_playbook(
            dirs["global"],
            "test",
            {"field1": "global", "field2": 100},
        )
        create_playbook(
            dirs["python"],
            "test",
            {"field1": "python", "field3": "new"},
        )

        resolver = PlaybookResolver(
            project_root=dirs["project_root"],
            project_type="python",
        )
        resolved = resolver.resolve("test")

        assert resolved.final_config["field1"] == "python"  # Overridden
        assert resolved.final_config["field2"] == 100  # From global
        assert resolved.final_config["field3"] == "new"  # From python

    def test_merge_nested_dicts(self, temp_playbook_dirs):
        """Test recursive merge of nested dicts."""
        dirs = temp_playbook_dirs
        create_playbook(
            dirs["global"],
            "test",
            {
                "config": {
                    "level1": {"a": 1, "b": 2},
                    "level2": "value",
                }
            },
        )
        create_playbook(
            dirs["python"],
            "test",
            {
                "config": {
                    "level1": {"b": 20, "c": 3},
                }
            },
        )

        resolver = PlaybookResolver(
            project_root=dirs["project_root"],
            project_type="python",
        )
        resolved = resolver.resolve("test")

        # Nested dict should be recursively merged
        assert resolved.final_config["config"]["level1"]["a"] == 1  # From global
        assert resolved.final_config["config"]["level1"]["b"] == 20  # Overridden
        assert resolved.final_config["config"]["level1"]["c"] == 3  # From python
        assert resolved.final_config["config"]["level2"] == "value"  # From global

    def test_merge_lists_replaced(self, temp_playbook_dirs):
        """Test that lists are replaced by default."""
        dirs = temp_playbook_dirs
        create_playbook(
            dirs["global"],
            "test",
            {"patterns": ["error1", "error2"]},
        )
        create_playbook(
            dirs["python"],
            "test",
            {"patterns": ["error3"]},
        )

        resolver = PlaybookResolver(
            project_root=dirs["project_root"],
            project_type="python",
        )
        resolved = resolver.resolve("test")

        # By default, lists are replaced
        assert resolved.final_config["patterns"] == ["error3"]

    def test_merge_lists_concatenated(self, temp_playbook_dirs):
        """Test explicit list concatenation with merge_lists flag."""
        dirs = temp_playbook_dirs
        create_playbook(
            dirs["global"],
            "test",
            {"patterns": ["error1", "error2"]},
        )
        create_playbook(
            dirs["python"],
            "test",
            {"patterns": ["error3"], "patterns_merge_lists": True},
        )

        resolver = PlaybookResolver(
            project_root=dirs["project_root"],
            project_type="python",
        )
        resolved = resolver.resolve("test")

        # With merge_lists flag, lists are concatenated
        # Merge flag must be in the override layer
        assert "error1" in resolved.final_config["patterns"]
        assert "error2" in resolved.final_config["patterns"]
        assert "error3" in resolved.final_config["patterns"]


class TestInheritance:
    """Test 'extends' inheritance syntax."""

    def test_extends_base_playbook(self, temp_playbook_dirs):
        """Test playbook extending another playbook."""
        dirs = temp_playbook_dirs
        create_playbook(
            dirs["global"],
            "base-error-fix",
            {"timeout": "fast", "severity": "medium", "version": 1},
        )
        create_playbook(
            dirs["global"],
            "type-error-fix",
            {
                "extends": "base-error-fix",
                "trigger": {"patterns": ["TypeError"]},
                "severity": "high",
            },
        )

        resolver = PlaybookResolver(
            project_root=dirs["project_root"],
            project_type="python",
        )
        resolved = resolver.resolve("type-error-fix")

        # Inheritance chain includes full path components
        assert any("base-error-fix" in item for item in resolved.inheritance_chain)
        assert any("type-error-fix" in item for item in resolved.inheritance_chain)
        assert resolved.final_config["timeout"] == "fast"  # From base
        assert resolved.final_config["severity"] == "high"  # Overridden
        assert resolved.final_config["trigger"]["patterns"] == ["TypeError"]

    def test_extends_with_layer_override(self, temp_playbook_dirs):
        """Test extends with layer-specific overrides."""
        dirs = temp_playbook_dirs
        create_playbook(
            dirs["global"],
            "base-error-fix",
            {"timeout": "fast", "severity": "medium"},
        )
        create_playbook(
            dirs["global"],
            "type-error-fix",
            {"extends": "base-error-fix", "trigger": {"patterns": ["TypeError"]}},
        )
        create_playbook(
            dirs["python"],
            "type-error-fix",
            {"severity": "high"},
        )

        resolver = PlaybookResolver(
            project_root=dirs["project_root"],
            project_type="python",
        )
        resolved = resolver.resolve("type-error-fix")

        # Resolution order: base → global extends → python override
        assert resolved.final_config["timeout"] == "fast"  # From base
        assert resolved.final_config["severity"] == "high"  # From python override
        assert resolved.final_config["trigger"]["patterns"] == ["TypeError"]

    def test_extends_missing_base(self, temp_playbook_dirs):
        """Test error when extends references missing playbook."""
        dirs = temp_playbook_dirs
        create_playbook(
            dirs["global"],
            "type-error-fix",
            {"extends": "nonexistent-base"},
        )

        resolver = PlaybookResolver(
            project_root=dirs["project_root"],
            project_type="python",
        )

        with pytest.raises(FileNotFoundError):
            resolver.resolve("type-error-fix")

    def test_deep_inheritance_chain(self, temp_playbook_dirs):
        """Test inheritance chain tracking."""
        dirs = temp_playbook_dirs
        create_playbook(dirs["global"], "base", {"a": 1})
        create_playbook(
            dirs["global"],
            "middle",
            {"extends": "base", "b": 2},
        )
        create_playbook(
            dirs["global"],
            "final",
            {"extends": "middle", "c": 3},
        )

        resolver = PlaybookResolver(
            project_root=dirs["project_root"],
            project_type="python",
        )
        resolved = resolver.resolve("final")

        # Check inheritance chain order
        chain_ids = [x.split("/")[-1] for x in resolved.inheritance_chain]
        assert "base" in chain_ids
        assert "middle" in chain_ids
        assert "final" in chain_ids


class TestProjectTypeDetection:
    """Test project type auto-detection."""

    def test_detect_python(self, temp_playbook_dirs):
        """Test detection of Python projects."""
        dirs = temp_playbook_dirs
        (dirs["project_root"] / "pyproject.toml").touch()

        resolver = PlaybookResolver(project_root=dirs["project_root"])
        assert resolver.project_type == "python"

    def test_detect_typescript(self, temp_playbook_dirs):
        """Test detection of TypeScript projects."""
        dirs = temp_playbook_dirs
        (dirs["project_root"] / "tsconfig.json").touch()

        resolver = PlaybookResolver(project_root=dirs["project_root"])
        assert resolver.project_type == "typescript"

    def test_detect_go(self, temp_playbook_dirs):
        """Test detection of Go projects."""
        dirs = temp_playbook_dirs
        (dirs["project_root"] / "go.mod").touch()

        resolver = PlaybookResolver(project_root=dirs["project_root"])
        assert resolver.project_type == "go"

    def test_detect_none(self, temp_playbook_dirs):
        """Test when no project type can be detected."""
        dirs = temp_playbook_dirs
        resolver = PlaybookResolver(project_root=dirs["project_root"])
        assert resolver.project_type is None

    def test_explicit_type_overrides_detection(self, temp_playbook_dirs):
        """Test that explicit type overrides auto-detection."""
        dirs = temp_playbook_dirs
        (dirs["project_root"] / "pyproject.toml").touch()

        # Explicitly set to go, overriding python detection
        resolver = PlaybookResolver(
            project_root=dirs["project_root"],
            project_type="go",
        )
        assert resolver.project_type == "go"


class TestListAvailable:
    """Test listing available playbooks."""

    def test_list_available(self, temp_playbook_dirs):
        """Test listing available playbooks per layer."""
        dirs = temp_playbook_dirs
        create_playbook(dirs["global"], "global-pb", {})
        create_playbook(dirs["python"], "python-pb", {})
        create_playbook(dirs["local"], "local-pb", {})

        resolver = PlaybookResolver(
            project_root=dirs["project_root"],
            project_type="python",
        )
        available = resolver.list_available()

        assert "global-pb" in available["global"]
        assert "python-pb" in available["project_type"]
        assert "local-pb" in available["local"]

    def test_list_available_empty_layers(self, temp_playbook_dirs):
        """Test listing when some layers are empty."""
        dirs = temp_playbook_dirs
        create_playbook(dirs["global"], "global-pb", {})

        resolver = PlaybookResolver(
            project_root=dirs["project_root"],
            project_type="python",
        )
        available = resolver.list_available()

        assert "global-pb" in available["global"]
        assert available["project_type"] == []
        assert available["local"] == []

    def test_list_available_all_types(self, temp_playbook_dirs):
        """Test listing all playbooks across all project types."""
        dirs = temp_playbook_dirs
        create_playbook(dirs["global"], "global-pb", {})
        create_playbook(dirs["python"], "python-pb", {})
        create_playbook(dirs["typescript"], "ts-pb", {})

        resolver = PlaybookResolver(
            project_root=dirs["project_root"],
            project_type="python",
        )
        all_available = resolver.list_available_all_types()

        assert "python" in all_available
        assert "typescript" in all_available
        assert "global-pb" in all_available["python"]
        assert "python-pb" in all_available["python"]
        assert "global-pb" in all_available["typescript"]
        assert "ts-pb" in all_available["typescript"]


class TestCaching:
    """Test resolution caching."""

    def test_cache_hit(self, temp_playbook_dirs):
        """Test that cached playbooks are reused."""
        dirs = temp_playbook_dirs
        create_playbook(dirs["global"], "test", {"value": 1})

        resolver = PlaybookResolver(
            project_root=dirs["project_root"],
            project_type="python",
        )

        resolved1 = resolver.resolve("test")
        resolved2 = resolver.resolve("test")

        # Should be same object due to cache
        assert resolved1 is resolved2

    def test_clear_cache(self, temp_playbook_dirs):
        """Test cache clearing."""
        dirs = temp_playbook_dirs
        create_playbook(dirs["global"], "test", {"value": 1})

        resolver = PlaybookResolver(
            project_root=dirs["project_root"],
            project_type="python",
        )

        resolved1 = resolver.resolve("test")
        resolver.clear_cache()
        resolved2 = resolver.resolve("test")

        # Different objects after cache clear
        assert resolved1 is not resolved2
        # But same content
        assert resolved1.final_config == resolved2.final_config


class TestValidation:
    """Test playbook validation."""

    def test_validate_valid_playbook(self, temp_playbook_dirs):
        """Test validation of valid playbook."""
        dirs = temp_playbook_dirs
        create_playbook(
            dirs["global"],
            "test",
            {"trigger": {"patterns": ["error"]}, "timeout": "fast"},
        )

        resolver = PlaybookResolver(
            project_root=dirs["project_root"],
            project_type="python",
        )
        is_valid, errors = resolver.validate_playbook_config("test")

        assert is_valid
        assert errors == []

    def test_validate_invalid_playbook(self, temp_playbook_dirs):
        """Test validation of invalid playbook."""
        dirs = temp_playbook_dirs
        resolver = PlaybookResolver(
            project_root=dirs["project_root"],
            project_type="python",
        )

        is_valid, errors = resolver.validate_playbook_config("nonexistent")
        assert not is_valid
        assert len(errors) > 0

    def test_validate_with_schema(self, temp_playbook_dirs):
        """Test validation with schema."""
        dirs = temp_playbook_dirs
        create_playbook(dirs["global"], "test", {"trigger": "value"})

        resolver = PlaybookResolver(
            project_root=dirs["project_root"],
            project_type="python",
        )
        schema = {"required": ["trigger", "timeout"]}
        is_valid, errors = resolver.validate_playbook_config("test", schema)

        assert not is_valid
        assert any("timeout" in e for e in errors)


class TestExport:
    """Test playbook export functionality."""

    def test_export_resolved_playbook(self, temp_playbook_dirs):
        """Test exporting resolved playbook."""
        dirs = temp_playbook_dirs
        create_playbook(
            dirs["global"],
            "test",
            {"trigger": {"patterns": ["error"]}, "timeout": "fast"},
        )
        create_playbook(
            dirs["python"],
            "test",
            {"severity": "high"},
        )

        resolver = PlaybookResolver(
            project_root=dirs["project_root"],
            project_type="python",
        )

        export_path = dirs["project_root"] / "resolved_test.yaml"
        success = resolver.export_resolved_playbook("test", export_path)

        assert success
        assert export_path.exists()

        # Verify exported content
        with open(export_path) as f:
            exported = yaml.safe_load(f)

        assert exported["id"] == "test"
        assert "metadata" in exported
        assert "playbook" in exported
        assert exported["metadata"]["project_type"] == "python"
        assert "global" in exported["metadata"]["layers_applied"]
        assert "project-type:python" in exported["metadata"]["layers_applied"]


class TestResolvedPlaybookDataclass:
    """Test ResolvedPlaybook dataclass."""

    def test_to_dict(self):
        """Test conversion to dictionary."""
        resolved = ResolvedPlaybook(
            id="test",
            layers_applied=["global", "local"],
            final_config={"key": "value"},
            inheritance_chain=["base", "test"],
            resolution_path=Path("/some/path"),
        )

        d = resolved.to_dict()
        assert d["id"] == "test"
        assert d["layers_applied"] == ["global", "local"]
        assert d["final_config"] == {"key": "value"}
        assert d["inheritance_chain"] == ["base", "test"]
        assert d["resolution_path"] == "/some/path"


class TestErrorHandling:
    """Test error handling and edge cases."""

    def test_resolve_multi(self, temp_playbook_dirs):
        """Test resolving multiple playbooks."""
        dirs = temp_playbook_dirs
        create_playbook(dirs["global"], "pb1", {"a": 1})
        create_playbook(dirs["global"], "pb2", {"b": 2})

        resolver = PlaybookResolver(
            project_root=dirs["project_root"],
            project_type="python",
        )

        results = resolver.resolve_multi(["pb1", "pb2", "nonexistent"])

        assert "pb1" in results
        assert "pb2" in results
        assert results["pb1"].final_config["a"] == 1
        assert results["pb2"].final_config["b"] == 2

    def test_get_resolution_info(self, temp_playbook_dirs):
        """Test getting resolution information."""
        dirs = temp_playbook_dirs
        create_playbook(
            dirs["global"],
            "test",
            {"trigger": {"patterns": ["error"]}},
        )

        resolver = PlaybookResolver(
            project_root=dirs["project_root"],
            project_type="python",
        )

        info = resolver.get_resolution_info("test")

        assert info["id"] == "test"
        assert "global" in info["layers_applied"]
        assert info["project_type"] == "python"
        assert "trigger" in info["config_keys"]

    def test_get_resolution_info_nonexistent(self, temp_playbook_dirs):
        """Test getting resolution info for nonexistent playbook."""
        dirs = temp_playbook_dirs
        resolver = PlaybookResolver(
            project_root=dirs["project_root"],
            project_type="python",
        )

        info = resolver.get_resolution_info("nonexistent")
        assert "error" in info
