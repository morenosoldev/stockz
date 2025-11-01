"""
Configuration management for Recover-Bot.

Implements Pydantic-based configuration with support for:
- Environment variables
- .env file
- config/config.yaml file

Environment variables take precedence over YAML config.
"""

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppConfig(BaseSettings):
    """Application-level configuration."""

    name: str = Field(default="Recover-Bot", description="Application name")
    version: str = Field(default="1.0.0", description="Application version")
    debug: bool = Field(default=False, description="Enable debug mode")
    env: str = Field(default="development", description="Environment (development/production)")
    log_level: str = Field(default="INFO", description="Logging level")
    log_format: str = Field(default="json", description="Log format (json/text)")
    structured_logging: bool = Field(default=True, description="Enable structured logging")

    model_config = SettingsConfigDict(
        env_prefix="APP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


class DatabaseConfig(BaseSettings):
    """Database configuration."""

    url: str = Field(
        default="postgresql://recoverbot:recoverbot@localhost:5432/recoverbot",
        description="Database connection URL",
    )
    pool_size: int = Field(default=10, description="Connection pool size", ge=1, le=100)
    max_overflow: int = Field(default=20, description="Max overflow connections", ge=0, le=100)
    pool_timeout: int = Field(default=30, description="Pool timeout in seconds", ge=1)
    pool_recycle: int = Field(default=3600, description="Pool recycle time in seconds", ge=300)
    echo: bool = Field(default=False, description="Echo SQL statements")

    model_config = SettingsConfigDict(
        env_prefix="DB_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Validate database URL format."""
        if not v.startswith(("postgresql://", "postgresql+psycopg2://")):
            raise ValueError("Database URL must start with postgresql://")
        return v


class SchedulerConfig(BaseSettings):
    """Scheduler configuration."""

    cron_schedule: str = Field(
        default="30 16 * * *",
        description="Cron schedule for daily scans (UTC)",
    )
    timezone: str = Field(default="UTC", description="Scheduler timezone")
    enabled: bool = Field(default=True, description="Enable scheduler")
    max_instances: int = Field(default=1, description="Max concurrent job instances", ge=1)
    coalesce: bool = Field(
        default=True,
        description="Coalesce missed runs into a single run",
    )
    misfire_grace_time: int = Field(
        default=300,
        description="Grace time for misfired jobs (seconds)",
        ge=0,
    )

    model_config = SettingsConfigDict(
        env_prefix="SCHEDULER_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


class ScannerConfig(BaseSettings):
    """Scanner configuration."""

    universe_size: int = Field(
        default=2000,
        description="Number of tickers to scan",
        ge=1,
        le=10000,
    )
    concurrency: int = Field(
        default=50,
        description="Concurrent ticker processing",
        ge=1,
        le=200,
    )
    timeout: int = Field(
        default=600,
        description="Scanner timeout in seconds",
        ge=60,
        le=3600,
    )
    cache_ttl_seconds: int = Field(
        default=3600,
        description="Cache TTL in seconds",
        ge=60,
    )
    retry_attempts: int = Field(
        default=3,
        description="Number of retry attempts for failed requests",
        ge=0,
        le=10,
    )
    retry_backoff: float = Field(
        default=2.0,
        description="Exponential backoff multiplier",
        ge=1.0,
        le=10.0,
    )

    model_config = SettingsConfigDict(
        env_prefix="SCANNER_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


class CacheConfig(BaseSettings):
    """Cache configuration for data adapters."""

    cache_dir: str = Field(
        default="data/cache",
        description="Directory for cached data",
    )
    ttl_seconds: int = Field(
        default=3600,
        description="Default cache TTL in seconds (0 = no expiration)",
        ge=0,
    )
    use_compression: bool = Field(
        default=False,
        description="Whether to use compression (future feature)",
    )
    auto_cleanup: bool = Field(
        default=True,
        description="Automatically clean expired cache entries",
    )

    model_config = SettingsConfigDict(
        env_prefix="CACHE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


class DataSourceConfig(BaseSettings):
    """Data source configuration."""

    # Price data provider
    price_provider: str = Field(
        default="yahoo_finance",
        description="Price data provider (yahoo_finance, alpha_vantage)",
    )
    yahoo_finance_api_key: str | None = Field(
        default=None,
        description="Yahoo Finance API key (optional)",
    )
    alpha_vantage_api_key: str | None = Field(
        default=None,
        description="Alpha Vantage API key",
    )

    # News data
    news_api_key: str | None = Field(
        default=None,
        description="NewsAPI key",
    )

    # Reddit API (for sentiment strategy)
    reddit_client_id: str | None = Field(
        default=None,
        description="Reddit API client ID",
    )
    reddit_client_secret: str | None = Field(
        default=None,
        description="Reddit API client secret",
    )
    reddit_user_agent: str | None = Field(
        default=None,
        description="Reddit API user agent",
    )

    # General API settings
    api_timeout: int = Field(default=30, description="API request timeout (seconds)", ge=5)
    api_retry_attempts: int = Field(
        default=3,
        description="API retry attempts",
        ge=0,
        le=10,
    )

    # Cache configuration
    cache: CacheConfig = Field(
        default_factory=CacheConfig,
        description="Cache settings for data adapters",
    )

    model_config = SettingsConfigDict(
        env_prefix="",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("price_provider")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        """Validate price data provider."""
        valid_providers = ["yahoo_finance", "alpha_vantage"]
        if v not in valid_providers:
            raise ValueError(f"Invalid provider. Must be one of: {valid_providers}")
        return v


class StrategyConfig(BaseSettings):
    """Strategy configuration."""

    enabled_strategies: list[str] = Field(
        default=["drop5"],
        description="List of enabled strategies",
    )
    min_score_threshold: float = Field(
        default=0.5,
        description="Minimum score threshold for candidates",
        ge=0.0,
        le=1.0,
    )

    model_config = SettingsConfigDict(
        env_prefix="",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("enabled_strategies", mode="before")
    @classmethod
    def parse_strategies(cls, v: Any) -> list[str]:
        """Parse comma-separated strategies."""
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        if isinstance(v, list):
            return v
        return []


class FeatureConfig(BaseSettings):
    """Feature engineering configuration."""

    version: str = Field(default="1.0.0", description="Feature version")
    atr_window: int = Field(default=14, description="ATR window", ge=1, le=100)
    rsi_window: int = Field(default=14, description="RSI window", ge=2, le=100)
    sma_window: int = Field(default=50, description="SMA window", ge=2, le=200)
    volume_window: int = Field(default=20, description="Volume window", ge=2, le=100)

    model_config = SettingsConfigDict(
        env_prefix="FEATURE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


class EvaluationConfig(BaseSettings):
    """Evaluation and backtesting configuration."""

    recovery_window_days: int = Field(
        default=5,
        description="Recovery window in trading days",
        ge=1,
        le=30,
    )
    recovery_threshold_pct: float = Field(
        default=3.0,
        description="Recovery threshold percentage",
        ge=0.0,
        le=100.0,
    )

    model_config = SettingsConfigDict(
        env_prefix="",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


class APIConfig(BaseSettings):
    """API server configuration."""

    host: str = Field(default="0.0.0.0", description="API host")
    port: int = Field(default=8000, description="API port", ge=1, le=65535)
    docs_enabled: bool = Field(default=True, description="Enable API docs")
    cors_origins: list[str] = Field(
        default=["http://localhost:3000", "http://localhost:8000"],
        description="CORS allowed origins",
    )

    model_config = SettingsConfigDict(
        env_prefix="API_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_origins(cls, v: Any) -> list[str]:
        """Parse comma-separated origins."""
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        if isinstance(v, list):
            return v
        return []


class Config(BaseSettings):
    """Main configuration aggregator."""

    app: AppConfig = Field(default_factory=AppConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)
    scanner: ScannerConfig = Field(default_factory=ScannerConfig)
    datasources: DataSourceConfig = Field(default_factory=DataSourceConfig)
    strategies: StrategyConfig = Field(default_factory=StrategyConfig)
    features: FeatureConfig = Field(default_factory=FeatureConfig)
    evaluation: EvaluationConfig = Field(default_factory=EvaluationConfig)
    api: APIConfig = Field(default_factory=APIConfig)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @classmethod
    def from_yaml(cls, yaml_path: Path) -> "Config":
        """Load configuration from YAML file."""
        if not yaml_path.exists():
            raise FileNotFoundError(f"Config file not found: {yaml_path}")

        with open(yaml_path) as f:
            data = yaml.safe_load(f) or {}

        # Create nested config objects
        return cls(
            app=AppConfig(**data.get("app", {})),
            database=DatabaseConfig(**data.get("database", {})),
            scheduler=SchedulerConfig(**data.get("scheduler", {})),
            scanner=ScannerConfig(**data.get("scanner", {})),
            datasources=DataSourceConfig(**data.get("datasources", {})),
            strategies=StrategyConfig(**data.get("strategies", {})),
            features=FeatureConfig(**data.get("features", {})),
            evaluation=EvaluationConfig(**data.get("evaluation", {})),
            api=APIConfig(**data.get("api", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        """Export configuration as dictionary."""
        return {
            "app": self.app.model_dump(),
            "database": {
                **self.database.model_dump(),
                "url": "***REDACTED***",  # Don't expose credentials
            },
            "scheduler": self.scheduler.model_dump(),
            "scanner": self.scanner.model_dump(),
            "datasources": {
                **self.datasources.model_dump(),
                "yahoo_finance_api_key": (
                    "***REDACTED***" if self.datasources.yahoo_finance_api_key else None
                ),
                "alpha_vantage_api_key": (
                    "***REDACTED***" if self.datasources.alpha_vantage_api_key else None
                ),
                "news_api_key": "***REDACTED***" if self.datasources.news_api_key else None,
                "reddit_client_id": (
                    "***REDACTED***" if self.datasources.reddit_client_id else None
                ),
                "reddit_client_secret": (
                    "***REDACTED***" if self.datasources.reddit_client_secret else None
                ),
            },
            "strategies": self.strategies.model_dump(),
            "features": self.features.model_dump(),
            "evaluation": self.evaluation.model_dump(),
            "api": self.api.model_dump(),
        }


@lru_cache
def get_config(config_path: Path | None = None) -> Config:
    """
    Get application configuration.

    Configuration priority (highest to lowest):
    1. Environment variables
    2. .env file
    3. config.yaml file
    4. Default values

    Args:
        config_path: Optional path to YAML config file.
                    Defaults to config/config.yaml

    Returns:
        Config: Loaded configuration object
    """
    # Default config path
    if config_path is None:
        config_path = Path(__file__).parent.parent.parent / "config" / "config.yaml"

    # Load from YAML if exists, otherwise use defaults
    if config_path.exists():
        config = Config.from_yaml(config_path)
    else:
        config = Config()

    return config


def verify_config() -> bool:
    """
    Verify configuration is valid and complete.

    Returns:
        bool: True if configuration is valid

    Raises:
        ValueError: If configuration is invalid
    """
    try:
        config = get_config()

        # Verify database URL is set
        if not config.database.url:
            raise ValueError("DATABASE_URL is required")

        # Verify at least one strategy is enabled
        if not config.strategies.enabled_strategies:
            raise ValueError("At least one strategy must be enabled")

        # Verify feature windows are reasonable
        if config.features.atr_window < 2:
            raise ValueError("ATR window must be at least 2")

        # Verify recovery window
        if config.evaluation.recovery_window_days < 1:
            raise ValueError("Recovery window must be at least 1 day")

        return True

    except Exception as e:
        print(f"❌ Configuration verification failed: {e}")
        raise
