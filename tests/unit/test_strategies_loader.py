"""Tests for strategy loader module."""

from pathlib import Path

import pytest

from src.strategies.base import StrategyConfig
from src.strategies.loader import (
    StrategyLoadError,
    discover_strategy_paths,
    import_strategy_class,
    load_strategies,
    load_strategy,
    load_strategy_config,
    reload_strategy,
)


class TestDiscoverStrategyPaths:
    """Test discover_strategy_paths function."""

    def test_discovers_drop5_strategy(self):
        """Test that drop5 strategy is discovered."""
        paths = discover_strategy_paths()

        assert len(paths) >= 1
        assert any("drop5" in str(p) for p in paths)

    def test_returns_path_objects(self):
        """Test that returned paths are Path objects."""
        paths = discover_strategy_paths()

        for path in paths:
            assert isinstance(path, Path)
            assert path.name == "implementation.py"

    def test_only_includes_implementation_files(self):
        """Test that only implementation.py files are returned."""
        paths = discover_strategy_paths()

        for path in paths:
            assert path.name == "implementation.py"
            assert path.exists()


class TestLoadStrategyConfig:
    """Test load_strategy_config function."""

    def test_loads_drop5_config(self):
        """Test loading drop5 config.yml."""
        strategy_dir = Path(__file__).parent.parent.parent / "src/strategies/drop5"
        config = load_strategy_config(strategy_dir)

        assert isinstance(config, StrategyConfig)
        assert config.name == "drop5"
        assert config.version == "1.0.0"
        assert config.enabled is True

    def test_missing_config_raises_error(self, tmp_path):
        """Test that missing config.yml raises error."""
        fake_dir = tmp_path / "fake_strategy"
        fake_dir.mkdir()

        with pytest.raises(StrategyLoadError, match="Missing config.yml"):
            load_strategy_config(fake_dir)

    def test_empty_config_raises_error(self, tmp_path):
        """Test that empty config.yml raises error."""
        strategy_dir = tmp_path / "test_strategy"
        strategy_dir.mkdir()
        config_path = strategy_dir / "config.yml"
        config_path.write_text("")

        with pytest.raises(StrategyLoadError, match="Empty config.yml"):
            load_strategy_config(strategy_dir)

    def test_invalid_yaml_raises_error(self, tmp_path):
        """Test that invalid YAML raises error."""
        strategy_dir = tmp_path / "test_strategy"
        strategy_dir.mkdir()
        config_path = strategy_dir / "config.yml"
        config_path.write_text("invalid: yaml: syntax:")

        with pytest.raises(StrategyLoadError, match="Invalid YAML"):
            load_strategy_config(strategy_dir)

    def test_invalid_schema_raises_error(self, tmp_path):
        """Test that invalid schema raises error."""
        strategy_dir = tmp_path / "test_strategy"
        strategy_dir.mkdir()
        config_path = strategy_dir / "config.yml"
        # Missing required fields
        config_path.write_text("name: test")

        with pytest.raises(StrategyLoadError, match="Invalid config schema"):
            load_strategy_config(strategy_dir)


class TestImportStrategyClass:
    """Test import_strategy_class function."""

    def test_imports_drop5_strategy(self):
        """Test importing Drop5Strategy class."""
        impl_path = Path(__file__).parent.parent.parent / "src/strategies/drop5/implementation.py"
        strategy_class = import_strategy_class(impl_path)

        assert strategy_class is not None
        assert hasattr(strategy_class, "name")
        assert hasattr(strategy_class, "version")
        assert hasattr(strategy_class, "filters")

    def test_missing_file_raises_error(self, tmp_path):
        """Test that missing implementation.py raises error."""
        fake_path = tmp_path / "fake.py"

        with pytest.raises(StrategyLoadError):
            import_strategy_class(fake_path)

    def test_no_strategy_class_raises_error(self, tmp_path):
        """Test that file with no strategy class raises error."""
        impl_path = tmp_path / "implementation.py"
        impl_path.write_text("# Just a comment, no class")

        with pytest.raises(StrategyLoadError, match="No strategy class found"):
            import_strategy_class(impl_path)

    def test_import_error_raises_strategy_load_error(self, tmp_path):
        """Test that import errors are caught."""
        impl_path = tmp_path / "implementation.py"
        impl_path.write_text("import nonexistent_module")

        with pytest.raises(StrategyLoadError, match="Failed to import"):
            import_strategy_class(impl_path)


class TestLoadStrategy:
    """Test load_strategy function."""

    def test_loads_drop5_strategy(self):
        """Test loading complete drop5 strategy."""
        impl_path = Path(__file__).parent.parent.parent / "src/strategies/drop5/implementation.py"
        strategy = load_strategy(impl_path)

        assert strategy.name == "drop5"
        assert strategy.version == "1.0.0"
        assert strategy.config.enabled is True

    def test_validates_strategy_protocol(self):
        """Test that loaded strategy is validated."""
        impl_path = Path(__file__).parent.parent.parent / "src/strategies/drop5/implementation.py"
        strategy = load_strategy(impl_path)

        # Should have all required methods
        assert hasattr(strategy, "filters")
        assert hasattr(strategy, "features")
        assert hasattr(strategy, "score")
        assert hasattr(strategy, "label")


class TestLoadStrategies:
    """Test load_strategies function."""

    def test_loads_all_strategies(self):
        """Test loading all available strategies."""
        strategies = load_strategies()

        assert len(strategies) >= 1
        assert any(s.name == "drop5" for s in strategies)

    def test_enabled_only_filter(self):
        """Test loading only enabled strategies."""
        strategies = load_strategies(enabled_only=True)

        for strategy in strategies:
            assert strategy.config.enabled is True

    def test_handles_load_errors_gracefully(self):
        """Test that load errors don't crash the loader."""
        # This should not raise, even if some strategies fail
        strategies = load_strategies()

        # Should still load valid strategies
        assert isinstance(strategies, list)


class TestReloadStrategy:
    """Test reload_strategy function."""

    def test_reload_drop5_strategy(self):
        """Test reloading drop5 strategy."""
        strategy = reload_strategy("drop5")

        assert strategy is not None
        assert strategy.name == "drop5"
        assert strategy.version == "1.0.0"

    def test_reload_nonexistent_strategy_returns_none(self):
        """Test that reloading nonexistent strategy returns None."""
        strategy = reload_strategy("nonexistent_strategy")

        assert strategy is None


class TestStrategyLoadError:
    """Test StrategyLoadError exception."""

    def test_error_has_path_and_reason(self):
        """Test that error stores path and reason."""
        error = StrategyLoadError("/path/to/strategy", "Something went wrong")

        assert error.strategy_path == "/path/to/strategy"
        assert error.reason == "Something went wrong"
        assert "Something went wrong" in str(error)
