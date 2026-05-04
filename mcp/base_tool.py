from abc import ABC, abstractmethod
from typing import Any, Dict, List

class BaseTool(ABC):
    """Abstract base class for all MCP tools."""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """The unique identifier for the tool."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """A human-readable description of what the tool does."""
        pass

    @property
    @abstractmethod
    def input_schema(self) -> Dict[str, str]:
        """A dictionary mapping input parameter names to their type/description."""
        pass

    @property
    def tags(self) -> List[str]:
        """Optional metadata tags for filtering tools."""
        return []

    @abstractmethod
    def execute(self, **kwargs) -> Any:
        """Executes the tool logic with the provided inputs."""
        pass
