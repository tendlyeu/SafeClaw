"""Tests for the serve CLI command."""

from unittest.mock import patch

from safeclaw.cli.serve import _default_host


def test_default_host_no_docker():
    """Outside Docker, default host should be 127.0.0.1."""
    with (
        patch("safeclaw.cli.serve.Path") as mock_path,
        patch.dict("os.environ", {}, clear=True),
    ):
        mock_path.return_value.exists.return_value = False
        result = _default_host()
        assert result == "127.0.0.1"


def test_default_host_in_docker():
    """Inside Docker (/.dockerenv exists), default host should be 0.0.0.0."""
    with patch("safeclaw.cli.serve.Path") as mock_path:
        mock_path.return_value.exists.return_value = True
        result = _default_host()
        assert result == "0.0.0.0"


def test_default_host_container_env():
    """With CONTAINER env var set, default host should be 0.0.0.0."""
    with (
        patch("safeclaw.cli.serve.Path") as mock_path,
        patch.dict("os.environ", {"CONTAINER": "1"}),
    ):
        mock_path.return_value.exists.return_value = False
        result = _default_host()
        assert result == "0.0.0.0"
