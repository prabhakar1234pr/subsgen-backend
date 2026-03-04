import logging
import os
import tempfile
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)


class TempFileHandler:
    """Handles temporary file creation and cleanup."""

    def __init__(self):
        self.temp_dir = tempfile.gettempdir()
        self.session_files: list[Path] = []

    def create_temp_path(self, suffix: str) -> Path:
        """Create a unique temporary file path."""
        filename = f"{uuid.uuid4()}{suffix}"
        path = Path(self.temp_dir) / filename
        self.session_files.append(path)
        return path

    def save_upload(self, content: bytes, suffix: str) -> Path:
        """Save uploaded file content to a temporary file."""
        path = self.create_temp_path(suffix)
        path.write_bytes(content)
        return path

    def cleanup(self):
        """Remove all temporary files from this session."""
        logger.debug(f"[FILE] cleanup: {len(self.session_files)} files")
        for path in self.session_files:
            try:
                if path.exists():
                    os.remove(path)
            except Exception:
                pass
        self.session_files.clear()

    def cleanup_file(self, path: Path):
        """Remove a specific temporary file."""
        try:
            if path.exists():
                os.remove(path)
            if path in self.session_files:
                self.session_files.remove(path)
        except Exception:
            pass

