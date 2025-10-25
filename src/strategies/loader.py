"""Strategy loader for auto-discovery and dynamic importing.

This module scans the strategies directory for strategy implementations,
validates them, and loads their configurations.

Example:
    >>> from src.strategies.loader import load_strategies
    >>> strategies = load_strategies()
    >>> for strategy in strategies:
    ...     print(f"{strategy.name} v{strategy.version}")
    drop5 v1.0.0
"""

import importlib.util
import sys
from pathlib import Path

import yaml
from pydantic import ValidationError

from src.ops.logging import get_logger
from src.strategies.base import StrategyConfig, StrategyProtocol, validate_strategy

logger = get_logger(__name__)


class StrategyLoadError(Exception):
    """Raised when a strategy fails to load."""

    def __init__(self, strategy_path: str, reason: str):
        """Initialize error with strategy path and reason.

        Args:
            strategy_path: Path to the strategy that failed to load
            reason: Human-readable reason for failure
        """
        self.strategy_path = strategy_path
        self.reason = reason
        super().__init__(f"Failed to load strategy from {strategy_path}: {reason}")


def discover_strategy_paths() -> list[Path]:
    """Discover all strategy implementation paths.

    Scans the strategies directory for subdirectories containing
    implementation.py files.

    Returns:
        List of Path objects pointing to implementation.py files

    Example:
        >>> paths = discover_strategy_paths()
        >>> for path in paths:
        ...     print(path)
        /workspaces/stockz/src/strategies/drop5/implementation.py
    """
    strategies_dir = Path(__file__).parent
    implementation_files = []

    # Scan for strategy directories (ignore base.py, loader.py, etc.)
    for item in strategies_dir.iterdir():
        if not item.is_dir() or item.name.startswith("_"):
            continue

        implementation_path = item / "implementation.py"
        if implementation_path.exists():
            implementation_files.append(implementation_path)

    logger.info(
        "Discovered strategy implementations",
        count=len(implementation_files),
        paths=[str(p.parent.name) for p in implementation_files],
    )

    return implementation_files


def load_strategy_config(strategy_dir: Path) -> StrategyConfig:
    """Load and validate strategy configuration from config.yml.

    Args:
        strategy_dir: Directory containing the strategy

    Returns:
        Validated StrategyConfig instance

    Raises:
        StrategyLoadError: If config file missing or invalid

    Example:
        >>> config = load_strategy_config(Path("src/strategies/drop5"))
        >>> print(config.name)
        drop5
    """
    config_path = strategy_dir / "config.yml"

    if not config_path.exists():
        raise StrategyLoadError(str(strategy_dir), f"Missing config.yml at {config_path}")

    try:
        with open(config_path) as f:
            config_data = yaml.safe_load(f)

        if not config_data:
            raise StrategyLoadError(str(strategy_dir), "Empty config.yml file")

        # Validate using Pydantic
        config = StrategyConfig(**config_data)

        logger.debug(
            "Loaded strategy config",
            strategy=config.name,
            version=config.version,
            enabled=config.enabled,
            config_path=str(config_path),
        )

        return config

    except yaml.YAMLError as e:
        raise StrategyLoadError(str(strategy_dir), f"Invalid YAML: {e}") from e
    except ValidationError as e:
        raise StrategyLoadError(str(strategy_dir), f"Invalid config schema: {e}") from e
    except Exception as e:
        raise StrategyLoadError(str(strategy_dir), f"Unexpected error loading config: {e}") from e


def import_strategy_class(implementation_path: Path) -> type[StrategyProtocol]:
    """Dynamically import strategy class from implementation.py.

    Args:
        implementation_path: Path to implementation.py file

    Returns:
        Strategy class (uninstantiated)

    Raises:
        StrategyLoadError: If import fails or no valid strategy class found

    Example:
        >>> path = Path("src/strategies/drop5/implementation.py")
        >>> strategy_class = import_strategy_class(path)
        >>> print(strategy_class.__name__)
        Drop5Strategy
    """
    strategy_dir = implementation_path.parent
    module_name = f"src.strategies.{strategy_dir.name}.implementation"

    try:
        # Import the module
        spec = importlib.util.spec_from_file_location(module_name, implementation_path)
        if spec is None or spec.loader is None:
            raise StrategyLoadError(str(implementation_path), "Failed to create module spec")

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        # Find strategy class (look for classes that implement StrategyProtocol)
        # Exclude BaseStrategy and other base classes
        from src.strategies.base import BaseStrategy

        strategy_classes = []
        for attr_name in dir(module):
            if attr_name.startswith("_"):
                continue

            attr = getattr(module, attr_name)
            if not isinstance(attr, type):
                continue

            # Skip BaseStrategy itself
            if attr is BaseStrategy:
                continue

            # Check if it looks like a strategy (has required attributes)
            if hasattr(attr, "name") and hasattr(attr, "version") and hasattr(attr, "filters"):
                strategy_classes.append(attr)

        if not strategy_classes:
            raise StrategyLoadError(
                str(implementation_path),
                "No strategy class found (must have name, version, filters attributes)",
            )

        if len(strategy_classes) > 1:
            logger.warning(
                "Multiple strategy classes found, using first one",
                path=str(implementation_path),
                classes=[cls.__name__ for cls in strategy_classes],
            )

        strategy_class = strategy_classes[0]

        logger.debug(
            "Imported strategy class",
            module=module_name,
            class_name=strategy_class.__name__,
            path=str(implementation_path),
        )

        return strategy_class

    except StrategyLoadError:
        raise
    except Exception as e:
        raise StrategyLoadError(str(implementation_path), f"Failed to import: {e}") from e


def load_strategy(implementation_path: Path) -> StrategyProtocol:
    """Load a single strategy from implementation.py.

    This function:
    1. Loads the config.yml
    2. Imports the strategy class
    3. Validates against StrategyProtocol
    4. Instantiates the strategy with config

    Args:
        implementation_path: Path to strategy implementation.py

    Returns:
        Instantiated strategy instance

    Raises:
        StrategyLoadError: If loading or validation fails

    Example:
        >>> path = Path("src/strategies/drop5/implementation.py")
        >>> strategy = load_strategy(path)
        >>> print(f"{strategy.name} v{strategy.version}")
        drop5 v1.0.0
    """
    strategy_dir = implementation_path.parent

    try:
        # Load config
        config = load_strategy_config(strategy_dir)

        # Import class
        strategy_class = import_strategy_class(implementation_path)

        # Instantiate strategy
        # Note: mypy doesn't know about strategy __init__, so we suppress the check
        strategy: StrategyProtocol = strategy_class(config=config)  # type: ignore[call-arg]

        # Validate against protocol
        validate_strategy(strategy)

        logger.info(
            "Loaded strategy",
            name=strategy.name,
            version=strategy.version,
            enabled=config.enabled,
            path=str(strategy_dir.name),
        )

        return strategy

    except StrategyLoadError:
        raise
    except Exception as e:
        raise StrategyLoadError(str(implementation_path), f"Unexpected error: {e}") from e


def load_strategies(enabled_only: bool = False) -> list[StrategyProtocol]:
    """Load all strategies from the strategies directory.

    Args:
        enabled_only: If True, only load strategies with enabled=True in config

    Returns:
        List of loaded strategy instances

    Example:
        >>> strategies = load_strategies(enabled_only=True)
        >>> for strategy in strategies:
        ...     print(f"{strategy.name} - {strategy.config.enabled}")
        drop5 - True
    """
    implementation_paths = discover_strategy_paths()
    loaded_strategies = []
    errors = []

    for path in implementation_paths:
        try:
            strategy = load_strategy(path)

            # Filter by enabled status if requested
            if enabled_only and not strategy.config.enabled:
                logger.debug(
                    "Skipping disabled strategy",
                    name=strategy.name,
                    enabled=strategy.config.enabled,
                )
                continue

            loaded_strategies.append(strategy)

        except StrategyLoadError as e:
            logger.error(
                "Failed to load strategy",
                path=str(path),
                error=e.reason,
                exc_info=True,
            )
            errors.append((path, e))
            continue

    logger.info(
        "Strategy loading complete",
        total_discovered=len(implementation_paths),
        successfully_loaded=len(loaded_strategies),
        errors=len(errors),
        enabled_only=enabled_only,
    )

    if errors:
        logger.warning(
            "Some strategies failed to load",
            failed_count=len(errors),
            failed_paths=[str(path) for path, _ in errors],
        )

    return loaded_strategies


def reload_strategy(strategy_name: str) -> StrategyProtocol | None:
    """Reload a specific strategy by name.

    Useful for development when strategy code changes.

    Args:
        strategy_name: Name of strategy to reload

    Returns:
        Reloaded strategy instance, or None if not found

    Example:
        >>> strategy = reload_strategy("drop5")
        >>> print(strategy.version)
        1.0.1
    """
    strategies_dir = Path(__file__).parent
    strategy_dir = strategies_dir / strategy_name
    implementation_path = strategy_dir / "implementation.py"

    if not implementation_path.exists():
        logger.error(
            "Strategy not found for reload",
            name=strategy_name,
            path=str(implementation_path),
        )
        return None

    try:
        # Remove from sys.modules to force reload
        module_name = f"src.strategies.{strategy_name}.implementation"
        if module_name in sys.modules:
            del sys.modules[module_name]

        strategy = load_strategy(implementation_path)

        logger.info("Strategy reloaded", name=strategy.name, version=strategy.version)

        return strategy

    except StrategyLoadError as e:
        logger.error("Failed to reload strategy", name=strategy_name, error=e.reason, exc_info=True)
        return None
