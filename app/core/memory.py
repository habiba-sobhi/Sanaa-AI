"""Conversation History and Session Management.

Defines an abstract BaseSessionStorage interface so storage backends
(In-Memory for Milestone 1, SQLite/Redis/Postgres for future milestones)
can be swapped seamlessly without altering chat orchestration logic.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional
from datetime import datetime, timezone


class BaseSessionStorage(ABC):
    """Abstract interface for session conversation storage."""

    @abstractmethod
    def get_history(self, session_id: str) -> List[Dict[str, str]]:
        """Retrieve conversation history turns for a session.

        Returns a list of dicts: [{"role": "user"|"model", "content": "..."}]
        """
        pass

    @abstractmethod
    def add_turn(
        self,
        session_id: str,
        user_message: str,
        assistant_reply: str,
    ) -> None:
        """Add a complete user-assistant turn to session history."""
        pass

    @abstractmethod
    def clear_history(self, session_id: str) -> bool:
        """Clear conversation history for a given session."""
        pass

    @abstractmethod
    def session_exists(self, session_id: str) -> bool:
        """Check if a session exists."""
        pass


class InMemorySessionStorage(BaseSessionStorage):
    """Lightweight in-memory session manager with a sliding window.

    Stores conversation in RAM, perfect for development and low-resource
    laptops. When MAX_HISTORY_TURNS is reached, older turns are pruned.
    """

    def __init__(self, max_turns: int = 10):
        self.max_turns = max_turns
        self._storage: Dict[str, List[Dict[str, str]]] = {}
        self._timestamps: Dict[str, datetime] = {}

    def get_history(self, session_id: str) -> List[Dict[str, str]]:
        return list(self._storage.get(session_id, []))

    def add_turn(
        self,
        session_id: str,
        user_message: str,
        assistant_reply: str,
    ) -> None:
        if session_id not in self._storage:
            self._storage[session_id] = []

        history = self._storage[session_id]

        # Add user and model messages
        history.append({"role": "user", "content": user_message})
        history.append({"role": "model", "content": assistant_reply})

        # Apply sliding window: keep last (max_turns * 2) entries
        max_messages = self.max_turns * 2
        if len(history) > max_messages:
            self._storage[session_id] = history[-max_messages:]

        self._timestamps[session_id] = datetime.now(timezone.utc)

    def clear_history(self, session_id: str) -> bool:
        if session_id in self._storage:
            del self._storage[session_id]
            self._timestamps.pop(session_id, None)
            return True
        return False

    def session_exists(self, session_id: str) -> bool:
        return session_id in self._storage


# Singleton in-memory instance for Milestone 1
_memory_store_instance: Optional[BaseSessionStorage] = None


def get_session_storage(max_turns: int = 10) -> BaseSessionStorage:
    """Dependency provider for session storage."""
    global _memory_store_instance
    if _memory_store_instance is None:
        _memory_store_instance = InMemorySessionStorage(max_turns=max_turns)
    return _memory_store_instance
