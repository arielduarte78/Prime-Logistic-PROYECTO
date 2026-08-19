"""stochopti/core/exceptions.py — Domain specific exception hierarchy."""

class StochoptiError(Exception):
    """Base exception for all Stochopti errors."""
    pass

class NodeNotFoundError(StochoptiError, KeyError):
    """Raised when a requested node does not exist in the graph topology."""
    pass

class InfeasibleConstraintsError(StochoptiError, ValueError):
    """Raised when no path exists in the graph that satisfies the provided epsilon bounds."""
    pass

class SharedMemoryCorruptionError(StochoptiError, RuntimeError):
    """Raised on synchronization failure or inconsistency in POSIX shared memory buffers."""
    pass
