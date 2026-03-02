"""Tests for MCP server tools."""
import sys
from unittest.mock import patch, MagicMock

# Mock FastMCP so tests work without mcp package installed
mock_fastmcp_module = MagicMock()
mock_mcp_instance = MagicMock()
mock_mcp_instance.tool.return_value = lambda fn: fn  # decorator passes through
mock_fastmcp_module.FastMCP.return_value = mock_mcp_instance
sys.modules['mcp'] = MagicMock()
sys.modules['mcp.server'] = MagicMock()
sys.modules['mcp.server.fastmcp'] = mock_fastmcp_module

from iobox.mcp_server import search_gmail, get_email, save_email, send_email, forward_gmail, check_auth  # noqa: E402


class TestMCPTools:
    def test_search_gmail(self):
        with patch("iobox.mcp_server.get_gmail_service") as mock_svc, \
             patch("iobox.mcp_server.search_emails", return_value=[{"message_id": "m1"}]) as mock_search:
            mock_svc.return_value = MagicMock()
            result = search_gmail("from:test@example.com", max_results=5, days=3)
            assert result == [{"message_id": "m1"}]
            mock_search.assert_called_once()

    def test_search_gmail_with_dates(self):
        with patch("iobox.mcp_server.get_gmail_service") as mock_svc, \
             patch("iobox.mcp_server.search_emails", return_value=[]) as mock_search:
            mock_svc.return_value = MagicMock()
            result = search_gmail(
                "subject:report",
                max_results=20,
                days=0,
                start_date="2024/01/01",
                end_date="2024/01/31",
            )
            assert result == []
            mock_search.assert_called_once_with(
                mock_svc.return_value, "subject:report", 20, 0, "2024/01/01", "2024/01/31"
            )

    def test_get_email(self):
        with patch("iobox.mcp_server.get_gmail_service") as mock_svc, \
             patch("iobox.mcp_server.get_email_content", return_value={"message_id": "m1", "subject": "Test"}) as mock_get:
            mock_svc.return_value = MagicMock()
            result = get_email("m1")
            assert result["subject"] == "Test"
            mock_get.assert_called_once_with(mock_svc.return_value, "m1")

    def test_save_email(self):
        with patch("iobox.mcp_server.get_gmail_service") as mock_svc, \
             patch("iobox.mcp_server.get_email_content", return_value={"message_id": "m1"}) as mock_get, \
             patch("iobox.mcp_server.convert_email_to_markdown", return_value="# Email") as mock_convert, \
             patch("iobox.mcp_server.create_output_directory", return_value="/tmp/out") as mock_dir, \
             patch("iobox.mcp_server.save_email_to_markdown", return_value="/tmp/out/email.md") as mock_save:
            mock_svc.return_value = MagicMock()
            result = save_email("m1", output_dir="/tmp/out")
            assert result == "/tmp/out/email.md"
            mock_get.assert_called_once_with(mock_svc.return_value, "m1", preferred_content_type="text/html")
            mock_convert.assert_called_once_with({"message_id": "m1"})
            mock_dir.assert_called_once_with("/tmp/out")
            mock_save.assert_called_once_with({"message_id": "m1"}, "# Email", "/tmp/out")

    def test_save_email_plain_text(self):
        with patch("iobox.mcp_server.get_gmail_service") as mock_svc, \
             patch("iobox.mcp_server.get_email_content", return_value={"message_id": "m2"}) as mock_get, \
             patch("iobox.mcp_server.convert_email_to_markdown", return_value="# Email plain"), \
             patch("iobox.mcp_server.create_output_directory", return_value="/tmp/out"), \
             patch("iobox.mcp_server.save_email_to_markdown", return_value="/tmp/out/email.md"):
            mock_svc.return_value = MagicMock()
            save_email("m2", output_dir="/tmp/out", prefer_html=False)
            mock_get.assert_called_once_with(mock_svc.return_value, "m2", preferred_content_type="text/plain")

    def test_send_email(self):
        with patch("iobox.mcp_server.get_gmail_service") as mock_svc, \
             patch("iobox.mcp_server.compose_message", return_value={"raw": "dGVzdA=="}) as mock_compose, \
             patch("iobox.mcp_server.send_message", return_value={"id": "sent-1"}) as mock_send:
            mock_svc.return_value = MagicMock()
            result = send_email("bob@example.com", "Hello", "Body text")
            assert result["id"] == "sent-1"
            mock_compose.assert_called_once_with(
                to="bob@example.com", subject="Hello", body="Body text", cc=None, bcc=None
            )
            mock_send.assert_called_once_with(mock_svc.return_value, {"raw": "dGVzdA=="})

    def test_send_email_with_cc_bcc(self):
        with patch("iobox.mcp_server.get_gmail_service") as mock_svc, \
             patch("iobox.mcp_server.compose_message", return_value={"raw": "dGVzdA=="}) as mock_compose, \
             patch("iobox.mcp_server.send_message", return_value={"id": "sent-2"}):
            mock_svc.return_value = MagicMock()
            send_email("bob@example.com", "Hi", "Body", cc="cc@example.com", bcc="bcc@example.com")
            mock_compose.assert_called_once_with(
                to="bob@example.com", subject="Hi", body="Body",
                cc="cc@example.com", bcc="bcc@example.com"
            )

    def test_forward_gmail(self):
        with patch("iobox.mcp_server.get_gmail_service") as mock_svc, \
             patch("iobox.mcp_server.forward_email", return_value={"id": "fwd-1"}) as mock_fwd:
            mock_svc.return_value = MagicMock()
            result = forward_gmail("m1", "bob@example.com", note="FYI")
            assert result["id"] == "fwd-1"
            mock_fwd.assert_called_once_with(
                mock_svc.return_value, message_id="m1", to="bob@example.com", additional_text="FYI"
            )

    def test_forward_gmail_no_note(self):
        with patch("iobox.mcp_server.get_gmail_service") as mock_svc, \
             patch("iobox.mcp_server.forward_email", return_value={"id": "fwd-2"}) as mock_fwd:
            mock_svc.return_value = MagicMock()
            result = forward_gmail("m2", "alice@example.com")
            assert result["id"] == "fwd-2"
            mock_fwd.assert_called_once_with(
                mock_svc.return_value, message_id="m2", to="alice@example.com", additional_text=None
            )

    def test_check_auth(self):
        with patch("iobox.mcp_server.check_auth_status", return_value={"authenticated": True}):
            result = check_auth()
            assert result["authenticated"] is True

    def test_check_auth_not_authenticated(self):
        with patch("iobox.mcp_server.check_auth_status", return_value={"authenticated": False, "token_file_exists": False}):
            result = check_auth()
            assert result["authenticated"] is False
            assert result["token_file_exists"] is False
