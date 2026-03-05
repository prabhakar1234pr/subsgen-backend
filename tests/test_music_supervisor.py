"""
tests/test_music_supervisor.py

E2E tests for MusicSupervisor agent (Agent 4).
"""

import pytest
from pathlib import Path
import tempfile

from agents.music_supervisor import find_and_download_music


class TestMusicSupervisor:
    """MusicSupervisor agent E2E tests."""

    def test_find_and_download_music_returns_path(
        self, sample_edit_plan, mock_key_manager, mock_groq, mock_httpx
    ):
        """MusicSupervisor downloads music and returns path."""
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            result = find_and_download_music(sample_edit_plan, out_dir)

            assert result is not None
            assert result.exists()
            assert result.suffix == ".mp3"

    def test_find_and_download_music_returns_none_when_no_results(
        self, sample_edit_plan, mock_key_manager, mock_groq
    ):
        """MusicSupervisor returns None when Internet Archive has no results."""
        from unittest.mock import patch, MagicMock

        def empty_ia_get(*args, **kwargs):
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.status_code = 200
            url = args[0] if args else ""
            if "advancedsearch" in str(url):
                resp.json.return_value = {"response": {"docs": []}}
            else:
                resp.json.return_value = {"files": []}
                resp.content = b""
            return resp

        with patch("agents.music_supervisor.httpx.Client") as mock_client:
            instance = MagicMock()
            instance.get = MagicMock(side_effect=empty_ia_get)
            instance.__enter__ = MagicMock(return_value=instance)
            instance.__exit__ = MagicMock(return_value=None)
            mock_client.return_value = instance

            with tempfile.TemporaryDirectory() as tmp:
                result = find_and_download_music(sample_edit_plan, Path(tmp))

        assert result is None

    def test_find_and_download_music_raises_without_api_keys(
        self, sample_edit_plan
    ):
        """MusicSupervisor raises when no Groq keys (for query refinement)."""
        with pytest.raises(RuntimeError, match="No Groq API keys"):
            find_and_download_music(sample_edit_plan, Path(tempfile.gettempdir()))
