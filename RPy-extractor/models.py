"""Data models and configuration for RPy Extractor."""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import threading


# ============================================================================
# Constants
# ============================================================================

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".svg", ".ico"}
AUDIO_EXTS = {".mp3", ".ogg", ".wav", ".m4a", ".aac", ".opus", ".flac"}
VIDEO_EXTS = {".mp4", ".webm", ".mov", ".m4v", ".mpeg", ".mpg"}

SKIP_DIRS = {".git", ".venv", "__pycache__"}
TRASH_DIR_NAME = ".trash"


# ============================================================================
# Configuration
# ============================================================================

@dataclass
class AppConfig:
    """Application configuration."""
    host: str
    port: int
    temp_path: Path
    output_dir_name: str
    merger_dir: Path
    web_dir_name: str
    log_dir: Path


# ============================================================================
# State Management
# ============================================================================

@dataclass
class SortState:
    """Manages sort session state."""
    lock: threading.Lock = field(default_factory=threading.Lock)
    session_id: str = ""
    assets_root: Path = field(default_factory=Path)
    assets: list[str] = field(default_factory=list)
    index: int = 0
    decision_by_asset: dict[str, str] = field(default_factory=dict)
    deleted_history: list[dict[str, Any]] = field(default_factory=list)
    trash_dir: Path = field(default_factory=Path)


@dataclass
class ExtractJobState:
    """Manages extract job state."""
    lock: threading.Lock = field(default_factory=threading.Lock)
    jobs: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass
class PersistentSessions:
    """Manages persistent sort sessions for resume capability with thread-safe access."""
    lock: threading.Lock = field(default_factory=threading.Lock)
    sessions: dict[str, dict[str, Any]] = field(default_factory=dict)

    def save_session(self, session_id: str, assets_root: Path, index: int, decisions: dict, history: list) -> None:
        """Save session state for resume capability.
        
        Args:
            session_id: Unique session identifier
            assets_root: Root path of assets being sorted
            index: Current position in asset list
            decisions: Dict of asset -> keep/delete decisions
            history: List of trash operations for undo
        """
        with self.lock:
            self.sessions[session_id] = {
                "assets_root": str(assets_root),
                "index": index,
                "decision_by_asset": decisions.copy(),
                "deleted_history": history.copy(),
            }
            print(f"[SESSION] Saved session {session_id}: index={index}, decisions={len(decisions)}, history={len(history)}")

    def get_session(self, session_id: str) -> dict | None:
        """Retrieve saved session by ID.
        
        Args:
            session_id: Session identifier to retrieve
            
        Returns:
            Session dict if found, None otherwise
        """
        with self.lock:
            session = self.sessions.get(session_id)
            if session:
                print(f"[SESSION] Retrieved session {session_id}")
            else:
                print(f"[SESSION] Session {session_id} not found")
            return session

    def list_sessions(self) -> list[str]:
        """List all session IDs (excluding current).
        
        Returns:
            List of session IDs
        """
        with self.lock:
            all_ids = list(self.sessions.keys())
            saved_ids = [sid for sid in all_ids if sid != "__current__"]
            print(f"[SESSION] Total sessions: {len(saved_ids)}")
            return saved_ids

    def get_current(self) -> dict | None:
        """Get current session state (temporary in-memory session).
        
        Returns:
            Current session dict or empty dict if none set
        """
        with self.lock:
            return self.sessions.get("__current__", {})

    def set_current(self, state: dict) -> None:
        """Set current session state (temporary in-memory).
        
        Args:
            state: Session state dict to store
        """
        with self.lock:
            self.sessions["__current__"] = state

    def clear(self) -> None:
        """Clear current session state."""
        with self.lock:
            if "__current__" in self.sessions:
                del self.sessions["__current__"]
                print("[SESSION] Cleared current session")


# Global state instances
SORT_STATE = SortState()
EXTRACT_JOBS = ExtractJobState()
SESSIONS = PersistentSessions()
