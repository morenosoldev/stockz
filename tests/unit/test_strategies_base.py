"""Tests for strategy base interfaces and protocols."""

from typing import Any

import pytest

from src.strategies.base import (
    BaseStrategy,
    StrategyConfig,
    StrategyProtocol,
    validate_strategy,
)


class TestStrategyConfig:
    """Test StrategyConfig pydantic model."""

    def test_valid_config(self):
        """Test creating valid strategy config."""
        config = StrategyConfig(
            name="test_strategy",
            version="1.0.0",
            description="Test strategy",
            enabled=True,
            parameters={"threshold": 0.5},
        )
        assert config.name == "test_strategy"
        assert config.version == "1.0.0"
        assert config.description == "Test strategy"
        assert config.enabled is True
        assert config.parameters == {"threshold": 0.5}

    def test_default_values(self):
        """Test default config values."""
        config = StrategyConfig(
            name="test",
            version="1.0.0",
            description="Test",
        )
        assert config.enabled is True
        assert config.parameters == {}

    def test_invalid_name_format(self):
        """Test invalid strategy name format."""
        with pytest.raises(ValueError):
            StrategyConfig(
                name="Test Strategy",  # Spaces not allowed
                version="1.0.0",
                description="Test",
            )

    def test_invalid_version_format(self):
        """Test invalid version format."""
        with pytest.raises(ValueError):
            StrategyConfig(
                name="test",
                version="1.0",  # Must be X.Y.Z
                description="Test",
            )

    def test_empty_description(self):
        """Test empty description not allowed."""
        with pytest.raises(ValueError):
            StrategyConfig(
                name="test",
                version="1.0.0",
                description="",
            )


class SimpleStrategy:
    """Minimal valid strategy implementation for testing."""

    name = "simple_strategy"
    version = "1.0.0"
    config = StrategyConfig(
        name="simple_strategy",
        version="1.0.0",
        description="Simple test strategy",
    )

    @property
    def config_schema(self):
        return StrategyConfig

    def filters(self, ticker_data: dict[str, Any]) -> bool:
        return ticker_data.get("volume", 0) > 1000000

    def features(self, ticker_data: dict[str, Any]) -> dict[str, Any]:
        return {"test_feature": 1.0}

    def score(self, features: dict[str, Any]) -> float:
        return 0.5

    def label(self, entry_data: dict[str, Any], outcome_data: dict[str, Any]) -> bool:
        return True


class TestStrategyProtocol:
    """Test StrategyProtocol interface."""

    def test_simple_strategy_is_protocol(self):
        """Test that simple strategy implements protocol."""
        strategy = SimpleStrategy()
        assert isinstance(strategy, StrategyProtocol)

    def test_protocol_name_property(self):
        """Test name property."""
        strategy = SimpleStrategy()
        assert strategy.name == "simple_strategy"

    def test_protocol_version_property(self):
        """Test version property."""
        strategy = SimpleStrategy()
        assert strategy.version == "1.0.0"

    def test_protocol_config_schema_property(self):
        """Test config_schema property."""
        strategy = SimpleStrategy()
        assert strategy.config_schema == StrategyConfig

    def test_protocol_filters_method(self):
        """Test filters method."""
        strategy = SimpleStrategy()
        assert strategy.filters({"volume": 2000000}) is True
        assert strategy.filters({"volume": 500000}) is False

    def test_protocol_features_method(self):
        """Test features method."""
        strategy = SimpleStrategy()
        features = strategy.features({})
        assert features == {"test_feature": 1.0}

    def test_protocol_score_method(self):
        """Test score method."""
        strategy = SimpleStrategy()
        score = strategy.score({})
        assert score == 0.5

    def test_protocol_label_method(self):
        """Test label method."""
        strategy = SimpleStrategy()
        result = strategy.label({}, {})
        assert result is True


class IncompleteStrategy:
    """Incomplete strategy missing required methods."""

    name = "incomplete"
    version = "1.0.0"

    @property
    def config_schema(self):
        return StrategyConfig

    # Missing: filters, features, score, label


class TestBaseStrategy:
    """Test BaseStrategy abstract base class."""

    def test_cannot_instantiate_directly(self):
        """Test BaseStrategy cannot be used directly."""
        with pytest.raises(NotImplementedError):
            strategy = BaseStrategy()
            _ = strategy.name

    def test_subclass_must_implement_name(self):
        """Test subclass must implement name property."""

        class TestStrategy(BaseStrategy):
            version = "1.0.0"

            def filters(self, ticker_data):
                return True

            def features(self, ticker_data):
                return {}

            def score(self, features):
                return 0.5

            def label(self, entry_data, outcome_data):
                return True

        with pytest.raises(NotImplementedError):
            strategy = TestStrategy()
            _ = strategy.name

    def test_subclass_must_implement_version(self):
        """Test subclass must implement version property."""

        class TestStrategy(BaseStrategy):
            name = "test"

            def filters(self, ticker_data):
                return True

            def features(self, ticker_data):
                return {}

            def score(self, features):
                return 0.5

            def label(self, entry_data, outcome_data):
                return True

        with pytest.raises(NotImplementedError):
            strategy = TestStrategy()
            _ = strategy.version

    def test_subclass_must_implement_filters(self):
        """Test subclass must implement filters method."""

        class TestStrategy(BaseStrategy):
            name = "test"
            version = "1.0.0"

            def features(self, ticker_data):
                return {}

            def score(self, features):
                return 0.5

            def label(self, entry_data, outcome_data):
                return True

        with pytest.raises(NotImplementedError):
            strategy = TestStrategy()
            strategy.filters({})

    def test_subclass_must_implement_features(self):
        """Test subclass must implement features method."""

        class TestStrategy(BaseStrategy):
            name = "test"
            version = "1.0.0"

            def filters(self, ticker_data):
                return True

            def score(self, features):
                return 0.5

            def label(self, entry_data, outcome_data):
                return True

        with pytest.raises(NotImplementedError):
            strategy = TestStrategy()
            strategy.features({})

    def test_subclass_must_implement_score(self):
        """Test subclass must implement score method."""

        class TestStrategy(BaseStrategy):
            name = "test"
            version = "1.0.0"

            def filters(self, ticker_data):
                return True

            def features(self, ticker_data):
                return {}

            def label(self, entry_data, outcome_data):
                return True

        with pytest.raises(NotImplementedError):
            strategy = TestStrategy()
            strategy.score({})

    def test_subclass_must_implement_label(self):
        """Test subclass must implement label method."""

        class TestStrategy(BaseStrategy):
            name = "test"
            version = "1.0.0"

            def filters(self, ticker_data):
                return True

            def features(self, ticker_data):
                return {}

            def score(self, features):
                return 0.5

        with pytest.raises(NotImplementedError):
            strategy = TestStrategy()
            strategy.label({}, {})

    def test_complete_subclass_works(self):
        """Test complete BaseStrategy subclass."""

        class TestStrategy(BaseStrategy):
            name = "test"
            version = "1.0.0"

            def filters(self, ticker_data):
                return True

            def features(self, ticker_data):
                return {"feature1": 1.0}

            def score(self, features):
                return 0.7

            def label(self, entry_data, outcome_data):
                return True

        strategy = TestStrategy()
        assert strategy.name == "test"
        assert strategy.version == "1.0.0"
        assert strategy.filters({}) is True
        assert strategy.features({}) == {"feature1": 1.0}
        assert strategy.score({}) == 0.7
        assert strategy.label({}, {}) is True

    def test_config_initialization(self):
        """Test strategy initialization with config."""

        class TestStrategy(BaseStrategy):
            name = "test"
            version = "1.0.0"

            def filters(self, ticker_data):
                return True

            def features(self, ticker_data):
                return {}

            def score(self, features):
                return 0.5

            def label(self, entry_data, outcome_data):
                return True

        config = StrategyConfig(
            name="test",
            version="1.0.0",
            description="Test",
            parameters={"threshold": 0.6},
        )
        strategy = TestStrategy(config=config)
        assert strategy.config.parameters["threshold"] == 0.6

    def test_default_config_schema(self):
        """Test default config_schema property."""

        class TestStrategy(BaseStrategy):
            name = "test"
            version = "1.0.0"

            def filters(self, ticker_data):
                return True

            def features(self, ticker_data):
                return {}

            def score(self, features):
                return 0.5

            def label(self, entry_data, outcome_data):
                return True

        strategy = TestStrategy()
        assert strategy.config_schema == StrategyConfig

    def test_logger_initialization(self):
        """Test logger is initialized."""

        class TestStrategy(BaseStrategy):
            name = "test"
            version = "1.0.0"

            def filters(self, ticker_data):
                return True

            def features(self, ticker_data):
                return {}

            def score(self, features):
                return 0.5

            def label(self, entry_data, outcome_data):
                return True

        strategy = TestStrategy()
        assert strategy.logger is not None
        assert hasattr(strategy.logger, "info")

    def test_validate_score_valid(self):
        """Test validate_score with valid score."""

        class TestStrategy(BaseStrategy):
            name = "test"
            version = "1.0.0"

            def filters(self, ticker_data):
                return True

            def features(self, ticker_data):
                return {}

            def score(self, features):
                return 0.5

            def label(self, entry_data, outcome_data):
                return True

        strategy = TestStrategy()
        assert strategy.validate_score(0.0) == 0.0
        assert strategy.validate_score(0.5) == 0.5
        assert strategy.validate_score(1.0) == 1.0

    def test_validate_score_clamps_negative(self):
        """Test validate_score clamps negative scores to 0.0."""

        class TestStrategy(BaseStrategy):
            name = "test"
            version = "1.0.0"

            def filters(self, ticker_data):
                return True

            def features(self, ticker_data):
                return {}

            def score(self, features):
                return 0.5

            def label(self, entry_data, outcome_data):
                return True

        strategy = TestStrategy()
        assert strategy.validate_score(-0.1) == 0.0
        assert strategy.validate_score(-10.0) == 0.0

    def test_validate_score_clamps_above_one(self):
        """Test validate_score clamps scores above 1.0."""

        class TestStrategy(BaseStrategy):
            name = "test"
            version = "1.0.0"

            def filters(self, ticker_data):
                return True

            def features(self, ticker_data):
                return {}

            def score(self, features):
                return 0.5

            def label(self, entry_data, outcome_data):
                return True

        strategy = TestStrategy()
        assert strategy.validate_score(1.1) == 1.0
        assert strategy.validate_score(10.0) == 1.0

    def test_validate_score_rejects_nan(self):
        """Test validate_score rejects NaN."""

        class TestStrategy(BaseStrategy):
            name = "test"
            version = "1.0.0"

            def filters(self, ticker_data):
                return True

            def features(self, ticker_data):
                return {}

            def score(self, features):
                return 0.5

            def label(self, entry_data, outcome_data):
                return True

        strategy = TestStrategy()
        with pytest.raises(ValueError, match="Invalid score"):
            strategy.validate_score(float("nan"))

    def test_validate_score_rejects_inf(self):
        """Test validate_score rejects infinity."""

        class TestStrategy(BaseStrategy):
            name = "test"
            version = "1.0.0"

            def filters(self, ticker_data):
                return True

            def features(self, ticker_data):
                return {}

            def score(self, features):
                return 0.5

            def label(self, entry_data, outcome_data):
                return True

        strategy = TestStrategy()
        with pytest.raises(ValueError, match="Invalid score"):
            strategy.validate_score(float("inf"))


class TestValidateStrategy:
    """Test validate_strategy function."""

    def test_valid_strategy(self):
        """Test validation passes for valid strategy."""
        strategy = SimpleStrategy()
        assert validate_strategy(strategy) is True

    def test_missing_name_property(self):
        """Test validation fails if name missing."""

        class BadStrategy:
            version = "1.0.0"
            config_schema = StrategyConfig

            def filters(self, ticker_data):
                return True

            def features(self, ticker_data):
                return {}

            def score(self, features):
                return 0.5

            def label(self, entry_data, outcome_data):
                return True

        with pytest.raises(TypeError, match="missing required property: name"):
            validate_strategy(BadStrategy())

    def test_missing_version_property(self):
        """Test validation fails if version missing."""

        class BadStrategy:
            name = "bad"
            config_schema = StrategyConfig

            def filters(self, ticker_data):
                return True

            def features(self, ticker_data):
                return {}

            def score(self, features):
                return 0.5

            def label(self, entry_data, outcome_data):
                return True

        with pytest.raises(TypeError, match="missing required property: version"):
            validate_strategy(BadStrategy())

    def test_missing_config_schema_property(self):
        """Test validation fails if config_schema missing."""

        class BadStrategy:
            name = "bad"
            version = "1.0.0"

            def filters(self, ticker_data):
                return True

            def features(self, ticker_data):
                return {}

            def score(self, features):
                return 0.5

            def label(self, entry_data, outcome_data):
                return True

        with pytest.raises(TypeError, match="missing required property: config_schema"):
            validate_strategy(BadStrategy())

    def test_missing_filters_method(self):
        """Test validation fails if filters missing."""

        class BadStrategy:
            name = "bad"
            version = "1.0.0"
            config_schema = StrategyConfig

            def features(self, ticker_data):
                return {}

            def score(self, features):
                return 0.5

            def label(self, entry_data, outcome_data):
                return True

        with pytest.raises(TypeError, match="missing required method: filters"):
            validate_strategy(BadStrategy())

    def test_missing_features_method(self):
        """Test validation fails if features missing."""

        class BadStrategy:
            name = "bad"
            version = "1.0.0"
            config_schema = StrategyConfig

            def filters(self, ticker_data):
                return True

            def score(self, features):
                return 0.5

            def label(self, entry_data, outcome_data):
                return True

        with pytest.raises(TypeError, match="missing required method: features"):
            validate_strategy(BadStrategy())

    def test_missing_score_method(self):
        """Test validation fails if score missing."""

        class BadStrategy:
            name = "bad"
            version = "1.0.0"
            config_schema = StrategyConfig

            def filters(self, ticker_data):
                return True

            def features(self, ticker_data):
                return {}

            def label(self, entry_data, outcome_data):
                return True

        with pytest.raises(TypeError, match="missing required method: score"):
            validate_strategy(BadStrategy())

    def test_missing_label_method(self):
        """Test validation fails if label missing."""

        class BadStrategy:
            name = "bad"
            version = "1.0.0"
            config_schema = StrategyConfig

            def filters(self, ticker_data):
                return True

            def features(self, ticker_data):
                return {}

            def score(self, features):
                return 0.5

        with pytest.raises(TypeError, match="missing required method: label"):
            validate_strategy(BadStrategy())

    def test_invalid_name_format_uppercase(self):
        """Test validation fails if name not lowercase."""

        class BadStrategy:
            name = "BadStrategy"  # Uppercase not allowed
            version = "1.0.0"
            config_schema = StrategyConfig

            def filters(self, ticker_data):
                return True

            def features(self, ticker_data):
                return {}

            def score(self, features):
                return 0.5

            def label(self, entry_data, outcome_data):
                return True

        with pytest.raises(TypeError, match="must be lowercase slug"):
            validate_strategy(BadStrategy())

    def test_invalid_name_format_spaces(self):
        """Test validation fails if name contains spaces."""

        class BadStrategy:
            name = "bad strategy"  # Spaces not allowed
            version = "1.0.0"
            config_schema = StrategyConfig

            def filters(self, ticker_data):
                return True

            def features(self, ticker_data):
                return {}

            def score(self, features):
                return 0.5

            def label(self, entry_data, outcome_data):
                return True

        with pytest.raises(TypeError, match="must be lowercase slug"):
            validate_strategy(BadStrategy())

    def test_invalid_version_format(self):
        """Test validation fails if version not semantic."""

        class BadStrategy:
            name = "bad"
            version = "1.0"  # Must be X.Y.Z
            config_schema = StrategyConfig

            def filters(self, ticker_data):
                return True

            def features(self, ticker_data):
                return {}

            def score(self, features):
                return 0.5

            def label(self, entry_data, outcome_data):
                return True

        with pytest.raises(TypeError, match="must be semantic version"):
            validate_strategy(BadStrategy())

    def test_non_string_version(self):
        """Test validation fails if version not string."""

        class BadStrategy:
            name = "bad"
            version = 1.0  # Must be string
            config_schema = StrategyConfig

            def filters(self, ticker_data):
                return True

            def features(self, ticker_data):
                return {}

            def score(self, features):
                return 0.5

            def label(self, entry_data, outcome_data):
                return True

        with pytest.raises(TypeError, match="version must be string"):
            validate_strategy(BadStrategy())
