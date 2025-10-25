"""Tests for configuration management."""

from pathlib import Path

import pytest

from src.ops.config import (
    APIConfig,
    AppConfig,
    Config,
    DatabaseConfig,
    DataSourceConfig,
    EvaluationConfig,
    FeatureConfig,
    ScannerConfig,
    SchedulerConfig,
    StrategyConfig,
    get_config,
    verify_config,
)


class TestAppConfig:
    """Test AppConfig class."""

    def test_default_values(self):
        """Test default configuration values."""
        config = AppConfig()
        assert config.name == "Recover-Bot"
        assert config.version == "1.0.0"
        assert config.debug is False
        assert config.env == "development"
        assert config.log_level == "INFO"

    def test_env_override(self, monkeypatch):
        """Test environment variable override."""
        monkeypatch.setenv("APP_DEBUG", "true")
        monkeypatch.setenv("APP_LOG_LEVEL", "DEBUG")
        config = AppConfig()
        assert config.debug is True
        assert config.log_level == "DEBUG"


class TestDatabaseConfig:
    """Test DatabaseConfig class."""

    def test_default_values(self):
        """Test default configuration values."""
        config = DatabaseConfig()
        assert config.url.startswith("postgresql://")
        assert config.pool_size == 10
        assert config.max_overflow == 20

    def test_url_validation(self):
        """Test database URL validation."""
        with pytest.raises(ValueError, match="must start with postgresql://"):
            DatabaseConfig(url="mysql://invalid")

    def test_valid_url_formats(self):
        """Test valid URL formats."""
        config1 = DatabaseConfig(url="postgresql://user:pass@host/db")
        assert config1.url.startswith("postgresql://")

        config2 = DatabaseConfig(url="postgresql+psycopg2://user:pass@host/db")
        assert config2.url.startswith("postgresql+psycopg2://")


class TestSchedulerConfig:
    """Test SchedulerConfig class."""

    def test_default_values(self):
        """Test default configuration values."""
        config = SchedulerConfig()
        assert config.cron_schedule == "30 16 * * *"
        assert config.timezone == "UTC"
        assert config.enabled is True
        assert config.max_instances == 1


class TestScannerConfig:
    """Test ScannerConfig class."""

    def test_default_values(self):
        """Test default configuration values."""
        config = ScannerConfig()
        assert config.universe_size == 2000
        assert config.concurrency == 50
        assert config.timeout == 600

    def test_validation_bounds(self):
        """Test validation bounds."""
        with pytest.raises(ValueError):
            ScannerConfig(universe_size=0)  # Below minimum

        with pytest.raises(ValueError):
            ScannerConfig(concurrency=300)  # Above maximum


class TestDataSourceConfig:
    """Test DataSourceConfig class."""

    def test_default_values(self):
        """Test default configuration values."""
        config = DataSourceConfig()
        assert config.price_provider == "yahoo_finance"
        assert config.api_timeout == 30

    def test_provider_validation(self):
        """Test provider validation."""
        with pytest.raises(ValueError, match="Invalid provider"):
            DataSourceConfig(price_provider="invalid_provider")

        # Valid providers should work
        config1 = DataSourceConfig(price_provider="yahoo_finance")
        assert config1.price_provider == "yahoo_finance"

        config2 = DataSourceConfig(price_provider="alpha_vantage")
        assert config2.price_provider == "alpha_vantage"


class TestStrategyConfig:
    """Test StrategyConfig class."""

    def test_default_values(self):
        """Test default configuration values."""
        config = StrategyConfig()
        assert config.enabled_strategies == ["drop5"]
        assert config.min_score_threshold == 0.5

    def test_parse_comma_separated_strategies(self, monkeypatch):
        """Test parsing comma-separated strategies from env."""
        # Pydantic Settings expects JSON format for lists from env vars
        monkeypatch.setenv("ENABLED_STRATEGIES", '["drop5","momentum","reversal"]')
        config = StrategyConfig()
        assert len(config.enabled_strategies) == 3
        assert "drop5" in config.enabled_strategies
        assert "momentum" in config.enabled_strategies


class TestFeatureConfig:
    """Test FeatureConfig class."""

    def test_default_values(self):
        """Test default configuration values."""
        config = FeatureConfig()
        assert config.version == "1.0.0"
        assert config.atr_window == 14
        assert config.rsi_window == 14
        assert config.sma_window == 50


class TestEvaluationConfig:
    """Test EvaluationConfig class."""

    def test_default_values(self):
        """Test default configuration values."""
        config = EvaluationConfig()
        assert config.recovery_window_days == 5
        assert config.recovery_threshold_pct == 3.0


class TestAPIConfig:
    """Test APIConfig class."""

    def test_default_values(self):
        """Test default configuration values."""
        config = APIConfig()
        assert config.host == "0.0.0.0"
        assert config.port == 8000
        assert config.docs_enabled is True

    def test_parse_comma_separated_origins(self, monkeypatch):
        """Test parsing comma-separated CORS origins from env."""
        # Pydantic Settings expects JSON format for lists from env vars
        monkeypatch.setenv("API_CORS_ORIGINS", '["http://localhost:3000","https://example.com"]')
        config = APIConfig()
        assert len(config.cors_origins) == 2


class TestMainConfig:
    """Test main Config class."""

    def test_default_instantiation(self):
        """Test creating config with defaults."""
        config = Config()
        assert config.app.name == "Recover-Bot"
        assert config.database.pool_size == 10
        assert config.scheduler.enabled is True

    def test_to_dict_redacts_secrets(self):
        """Test that to_dict redacts sensitive information."""
        config = Config()
        config.datasources.alpha_vantage_api_key = "secret_key_123"
        config.datasources.news_api_key = "news_key_456"

        config_dict = config.to_dict()

        # Check credentials are redacted
        assert config_dict["database"]["url"] == "***REDACTED***"
        assert config_dict["datasources"]["alpha_vantage_api_key"] == "***REDACTED***"
        assert config_dict["datasources"]["news_api_key"] == "***REDACTED***"

        # Check non-secret values are present
        assert config_dict["app"]["name"] == "Recover-Bot"
        assert config_dict["scanner"]["universe_size"] == 2000

    def test_from_yaml(self, tmp_path):
        """Test loading config from YAML file."""
        yaml_content = """
app:
  name: "Test-Bot"
  debug: true

database:
  pool_size: 5

scanner:
  universe_size: 500
"""
        yaml_file = tmp_path / "test_config.yaml"
        yaml_file.write_text(yaml_content)

        config = Config.from_yaml(yaml_file)
        assert config.app.name == "Test-Bot"
        assert config.app.debug is True
        assert config.database.pool_size == 5
        assert config.scanner.universe_size == 500

    def test_from_yaml_file_not_found(self):
        """Test error when YAML file doesn't exist."""
        with pytest.raises(FileNotFoundError):
            Config.from_yaml(Path("/nonexistent/config.yaml"))


class TestGetConfig:
    """Test get_config factory function."""

    def test_get_config_default(self):
        """Test getting config with default path."""
        config = get_config()
        assert isinstance(config, Config)
        assert config.app.name == "Recover-Bot"

    def test_get_config_custom_path(self, tmp_path):
        """Test getting config with custom path."""
        yaml_content = """
app:
  name: "Custom-Bot"
"""
        yaml_file = tmp_path / "custom_config.yaml"
        yaml_file.write_text(yaml_content)

        # Clear cache to allow new config
        get_config.cache_clear()

        config = get_config(yaml_file)
        assert config.app.name == "Custom-Bot"

        # Clean up cache
        get_config.cache_clear()

    def test_get_config_caching(self):
        """Test that get_config caches results."""
        get_config.cache_clear()

        config1 = get_config()
        config2 = get_config()

        # Should return same instance due to lru_cache
        assert config1 is config2

        get_config.cache_clear()


class TestVerifyConfig:
    """Test verify_config function."""

    def test_verify_valid_config(self):
        """Test verification of valid configuration."""
        get_config.cache_clear()
        assert verify_config() is True
        get_config.cache_clear()

    def test_verify_invalid_database_url(self, monkeypatch, tmp_path):
        """Test verification fails with invalid database URL."""
        get_config.cache_clear()

        yaml_content = """
database:
  url: ""
"""
        yaml_file = tmp_path / "invalid_config.yaml"
        yaml_file.write_text(yaml_content)

        with pytest.raises(ValueError):
            Config.from_yaml(yaml_file)

        get_config.cache_clear()

    def test_verify_no_strategies(self, tmp_path):
        """Test verification fails with no enabled strategies."""
        get_config.cache_clear()

        yaml_content = """
strategies:
  enabled_strategies: []
"""
        yaml_file = tmp_path / "no_strategies.yaml"
        yaml_file.write_text(yaml_content)

        # Temporarily replace get_config to use our test file
        def mock_get_config():
            return Config.from_yaml(yaml_file)

        import src.ops.config as config_module

        original_get_config = config_module.get_config
        config_module.get_config = mock_get_config

        try:
            with pytest.raises(ValueError, match="At least one strategy must be enabled"):
                verify_config()
        finally:
            config_module.get_config = original_get_config
            get_config.cache_clear()
