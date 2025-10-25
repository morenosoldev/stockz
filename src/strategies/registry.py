"""Strategy registry for managing loaded strategies.

This module provides a singleton registry for strategy instances,
allowing strategies to be registered, retrieved, and filtered.

Example:
    >>> from src.strategies.registry import StrategyRegistry
    >>> registry = StrategyRegistry()
    >>> registry.discover_and_register()
    >>> strategy = registry.get("drop5")
    >>> print(strategy.name)
    drop5
"""

from typing import Any

from src.ops.logging import get_logger
from src.strategies.base import StrategyProtocol
from src.strategies.loader import load_strategies

logger = get_logger(__name__)


class StrategyNotFoundError(Exception):
    """Raised when a requested strategy is not found in the registry."""

    def __init__(self, strategy_name: str):
        """Initialize error with strategy name.

        Args:
            strategy_name: Name of the strategy that was not found
        """
        self.strategy_name = strategy_name
        super().__init__(f"Strategy not found: {strategy_name}")


class StrategyRegistry:
    """Singleton registry for managing strategy instances.

    The registry maintains a collection of loaded strategies and provides
    methods to register, retrieve, and filter them.

    Example:
        >>> registry = StrategyRegistry()
        >>> registry.discover_and_register()
        >>> strategies = registry.list_strategies()
        >>> print(len(strategies))
        1
    """

    _instance: "StrategyRegistry | None" = None
    _strategies: dict[str, StrategyProtocol]

    def __new__(cls) -> "StrategyRegistry":
        """Implement singleton pattern.

        Returns:
            The single StrategyRegistry instance
        """
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._strategies = {}
            logger.debug("Created new StrategyRegistry instance")
        return cls._instance

    def __init__(self) -> None:
        """Initialize registry (no-op due to singleton pattern)."""
        # Don't re-initialize on subsequent calls
        pass

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton instance (useful for testing).

        Warning:
            This will clear all registered strategies. Use with caution.
        """
        if cls._instance is not None:
            cls._instance._strategies.clear()
            cls._instance = None
            logger.warning("StrategyRegistry reset - all strategies cleared")

    def register(self, strategy: StrategyProtocol) -> None:
        """Register a strategy instance.

        Args:
            strategy: Strategy instance to register

        Raises:
            TypeError: If strategy doesn't implement StrategyProtocol

        Example:
            >>> from src.strategies.base import BaseStrategy
            >>> class MyStrategy(BaseStrategy):
            ...     name = "test"
            ...     version = "1.0.0"
            ...     # ... implement required methods
            >>> registry.register(MyStrategy())
        """
        if not isinstance(strategy, StrategyProtocol):
            raise TypeError(f"Strategy must implement StrategyProtocol, got {type(strategy)}")

        strategy_name = strategy.name

        if strategy_name in self._strategies:
            logger.warning(
                "Replacing existing strategy",
                name=strategy_name,
                old_version=self._strategies[strategy_name].version,
                new_version=strategy.version,
            )

        self._strategies[strategy_name] = strategy

        logger.info(
            "Registered strategy",
            name=strategy_name,
            version=strategy.version,
            total_strategies=len(self._strategies),
        )

    def unregister(self, strategy_name: str) -> None:
        """Unregister a strategy by name.

        Args:
            strategy_name: Name of strategy to unregister

        Raises:
            StrategyNotFoundError: If strategy not found

        Example:
            >>> registry.unregister("drop5")
        """
        if strategy_name not in self._strategies:
            raise StrategyNotFoundError(strategy_name)

        strategy = self._strategies.pop(strategy_name)

        logger.info(
            "Unregistered strategy",
            name=strategy_name,
            version=strategy.version,
            remaining_strategies=len(self._strategies),
        )

    def get(self, strategy_name: str) -> StrategyProtocol:
        """Get a strategy by name.

        Args:
            strategy_name: Name of strategy to retrieve

        Returns:
            Strategy instance

        Raises:
            StrategyNotFoundError: If strategy not found

        Example:
            >>> strategy = registry.get("drop5")
            >>> print(strategy.version)
            1.0.0
        """
        if strategy_name not in self._strategies:
            raise StrategyNotFoundError(strategy_name)

        return self._strategies[strategy_name]

    def has(self, strategy_name: str) -> bool:
        """Check if a strategy is registered.

        Args:
            strategy_name: Name of strategy to check

        Returns:
            True if strategy is registered, False otherwise

        Example:
            >>> if registry.has("drop5"):
            ...     strategy = registry.get("drop5")
        """
        return strategy_name in self._strategies

    def list_strategies(
        self, enabled_only: bool = False, names_only: bool = False
    ) -> list[StrategyProtocol] | list[str]:
        """List all registered strategies.

        Args:
            enabled_only: If True, only return enabled strategies
            names_only: If True, return list of names instead of instances

        Returns:
            List of strategy instances or names

        Example:
            >>> strategies = registry.list_strategies(enabled_only=True)
            >>> names = registry.list_strategies(names_only=True)
            >>> print(names)
            ['drop5']
        """
        strategies = list(self._strategies.values())

        if enabled_only:
            strategies = [s for s in strategies if s.config.enabled]

        if names_only:
            return [s.name for s in strategies]

        return strategies

    def count(self, enabled_only: bool = False) -> int:
        """Count registered strategies.

        Args:
            enabled_only: If True, only count enabled strategies

        Returns:
            Number of strategies

        Example:
            >>> print(registry.count())
            1
        """
        if enabled_only:
            return len([s for s in self._strategies.values() if s.config.enabled])
        return len(self._strategies)

    def discover_and_register(self, enabled_only: bool = False) -> int:
        """Discover and register all strategies from the strategies directory.

        This method scans the strategies directory, loads all valid strategies,
        and registers them in the registry.

        Args:
            enabled_only: If True, only register enabled strategies

        Returns:
            Number of strategies successfully registered

        Example:
            >>> count = registry.discover_and_register()
            >>> print(f"Registered {count} strategies")
            Registered 1 strategies
        """
        logger.info("Starting strategy discovery and registration")

        try:
            strategies = load_strategies(enabled_only=enabled_only)

            for strategy in strategies:
                self.register(strategy)

            logger.info(
                "Strategy discovery complete",
                registered=len(strategies),
                enabled_only=enabled_only,
            )

            return len(strategies)

        except Exception as e:
            logger.error("Strategy discovery failed", error=str(e), exc_info=True)
            raise

    def get_metadata(self) -> dict[str, Any]:
        """Get metadata about all registered strategies.

        Returns:
            Dictionary with strategy metadata

        Example:
            >>> metadata = registry.get_metadata()
            >>> print(metadata)
            {
                'total': 1,
                'enabled': 1,
                'disabled': 0,
                'strategies': [
                    {'name': 'drop5', 'version': '1.0.0', 'enabled': True}
                ]
            }
        """
        strategies = list(self._strategies.values())
        enabled_count = sum(1 for s in strategies if s.config.enabled)

        return {
            "total": len(strategies),
            "enabled": enabled_count,
            "disabled": len(strategies) - enabled_count,
            "strategies": [
                {
                    "name": s.name,
                    "version": s.version,
                    "enabled": s.config.enabled,
                    "description": s.config.description,
                }
                for s in strategies
            ],
        }

    def clear(self) -> None:
        """Clear all registered strategies.

        Warning:
            This removes all strategies from the registry.

        Example:
            >>> registry.clear()
            >>> print(registry.count())
            0
        """
        count = len(self._strategies)
        self._strategies.clear()

        logger.warning("Cleared all strategies from registry", count=count)


# Global registry instance (singleton)
_registry = StrategyRegistry()


def get_registry() -> StrategyRegistry:
    """Get the global strategy registry instance.

    Returns:
        The singleton StrategyRegistry instance

    Example:
        >>> from src.strategies.registry import get_registry
        >>> registry = get_registry()
        >>> registry.discover_and_register()
    """
    return _registry
