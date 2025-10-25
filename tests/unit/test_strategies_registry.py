"""Tests for strategy registry module."""

import pytest

from src.strategies.base import BaseStrategy
from src.strategies.registry import (
    StrategyNotFoundError,
    StrategyRegistry,
    get_registry,
)


class SimpleTestStrategy(BaseStrategy):
    """Simple test strategy for testing."""

    name = "test_strategy"
    version = "1.0.0"

    def filters(self, ticker_data):
        return True

    def features(self, ticker_data):
        return {}

    def score(self, features):
        return 0.5

    def label(self, entry_data, outcome_data):
        return True


class AnotherTestStrategy(BaseStrategy):
    """Another test strategy."""

    name = "another_strategy"
    version = "2.0.0"

    def filters(self, ticker_data):
        return True

    def features(self, ticker_data):
        return {}

    def score(self, features):
        return 0.7

    def label(self, entry_data, outcome_data):
        return False


@pytest.fixture
def registry():
    """Create fresh registry for each test."""
    StrategyRegistry.reset()
    return StrategyRegistry()


class TestStrategyRegistry:
    """Test StrategyRegistry class."""

    def test_singleton_pattern(self, registry):
        """Test that registry uses singleton pattern."""
        registry1 = StrategyRegistry()
        registry2 = StrategyRegistry()

        assert registry1 is registry2

    def test_reset_clears_instance(self):
        """Test that reset clears the singleton instance."""
        registry1 = StrategyRegistry()
        registry1.register(SimpleTestStrategy())

        StrategyRegistry.reset()
        registry2 = StrategyRegistry()

        assert registry2.count() == 0

    def test_register_strategy(self, registry):
        """Test registering a strategy."""
        strategy = SimpleTestStrategy()
        registry.register(strategy)

        assert registry.count() == 1
        assert registry.has("test_strategy")

    def test_register_duplicate_replaces_old(self, registry):
        """Test that registering duplicate strategy replaces old one."""
        strategy1 = SimpleTestStrategy()
        strategy2 = SimpleTestStrategy()

        registry.register(strategy1)
        registry.register(strategy2)

        assert registry.count() == 1
        assert registry.get("test_strategy") is strategy2

    def test_register_invalid_type_raises_error(self, registry):
        """Test that registering invalid type raises TypeError."""
        with pytest.raises(TypeError, match="must implement StrategyProtocol"):
            registry.register("not a strategy")

    def test_unregister_strategy(self, registry):
        """Test unregistering a strategy."""
        strategy = SimpleTestStrategy()
        registry.register(strategy)
        registry.unregister("test_strategy")

        assert registry.count() == 0
        assert not registry.has("test_strategy")

    def test_unregister_nonexistent_raises_error(self, registry):
        """Test that unregistering nonexistent strategy raises error."""
        with pytest.raises(StrategyNotFoundError):
            registry.unregister("nonexistent")

    def test_get_strategy(self, registry):
        """Test getting a strategy by name."""
        strategy = SimpleTestStrategy()
        registry.register(strategy)

        retrieved = registry.get("test_strategy")

        assert retrieved is strategy
        assert retrieved.name == "test_strategy"

    def test_get_nonexistent_raises_error(self, registry):
        """Test that getting nonexistent strategy raises error."""
        with pytest.raises(StrategyNotFoundError):
            registry.get("nonexistent")

    def test_has_strategy(self, registry):
        """Test checking if strategy exists."""
        strategy = SimpleTestStrategy()
        registry.register(strategy)

        assert registry.has("test_strategy") is True
        assert registry.has("nonexistent") is False

    def test_list_strategies(self, registry):
        """Test listing all strategies."""
        strategy1 = SimpleTestStrategy()
        strategy2 = AnotherTestStrategy()

        registry.register(strategy1)
        registry.register(strategy2)

        strategies = registry.list_strategies()

        assert len(strategies) == 2
        assert strategy1 in strategies
        assert strategy2 in strategies

    def test_list_strategies_names_only(self, registry):
        """Test listing strategy names only."""
        strategy1 = SimpleTestStrategy()
        strategy2 = AnotherTestStrategy()

        registry.register(strategy1)
        registry.register(strategy2)

        names = registry.list_strategies(names_only=True)

        assert isinstance(names, list)
        assert len(names) == 2
        assert "test_strategy" in names
        assert "another_strategy" in names

    def test_list_strategies_enabled_only(self, registry):
        """Test listing only enabled strategies."""
        strategy1 = SimpleTestStrategy()
        strategy1.config.enabled = True

        strategy2 = AnotherTestStrategy()
        strategy2.config.enabled = False

        registry.register(strategy1)
        registry.register(strategy2)

        strategies = registry.list_strategies(enabled_only=True)

        assert len(strategies) == 1
        assert strategies[0].name == "test_strategy"

    def test_count_all_strategies(self, registry):
        """Test counting all strategies."""
        registry.register(SimpleTestStrategy())
        registry.register(AnotherTestStrategy())

        assert registry.count() == 2

    def test_count_enabled_only(self, registry):
        """Test counting only enabled strategies."""
        strategy1 = SimpleTestStrategy()
        strategy1.config.enabled = True

        strategy2 = AnotherTestStrategy()
        strategy2.config.enabled = False

        registry.register(strategy1)
        registry.register(strategy2)

        assert registry.count(enabled_only=True) == 1

    def test_discover_and_register(self, registry):
        """Test discovering and registering strategies."""
        count = registry.discover_and_register()

        assert count >= 1  # At least drop5 should be found
        assert registry.has("drop5")

    def test_discover_and_register_enabled_only(self, registry):
        """Test discovering only enabled strategies."""
        registry.discover_and_register(enabled_only=True)

        strategies = registry.list_strategies()
        for strategy in strategies:
            assert strategy.config.enabled is True

    def test_get_metadata(self, registry):
        """Test getting registry metadata."""
        strategy1 = SimpleTestStrategy()
        strategy1.config.enabled = True

        strategy2 = AnotherTestStrategy()
        strategy2.config.enabled = False

        registry.register(strategy1)
        registry.register(strategy2)

        metadata = registry.get_metadata()

        assert metadata["total"] == 2
        assert metadata["enabled"] == 1
        assert metadata["disabled"] == 1
        assert len(metadata["strategies"]) == 2

    def test_metadata_includes_strategy_info(self, registry):
        """Test that metadata includes strategy information."""
        strategy = SimpleTestStrategy()
        registry.register(strategy)

        metadata = registry.get_metadata()
        strategy_info = metadata["strategies"][0]

        assert strategy_info["name"] == "test_strategy"
        assert strategy_info["version"] == "1.0.0"
        assert "enabled" in strategy_info
        assert "description" in strategy_info

    def test_clear_strategies(self, registry):
        """Test clearing all strategies."""
        registry.register(SimpleTestStrategy())
        registry.register(AnotherTestStrategy())

        assert registry.count() == 2

        registry.clear()

        assert registry.count() == 0

    def test_clear_empty_registry(self, registry):
        """Test clearing empty registry doesn't error."""
        registry.clear()  # Should not raise

        assert registry.count() == 0


class TestGetRegistry:
    """Test get_registry function."""

    def test_returns_singleton_instance(self):
        """Test that get_registry returns the singleton."""
        StrategyRegistry.reset()

        registry1 = get_registry()
        registry2 = get_registry()

        assert registry1 is registry2

    def test_returns_registry_instance(self):
        """Test that get_registry returns StrategyRegistry."""
        StrategyRegistry.reset()

        registry = get_registry()

        assert isinstance(registry, StrategyRegistry)


class TestStrategyNotFoundError:
    """Test StrategyNotFoundError exception."""

    def test_error_has_strategy_name(self):
        """Test that error stores strategy name."""
        error = StrategyNotFoundError("test_strategy")

        assert error.strategy_name == "test_strategy"
        assert "test_strategy" in str(error)
