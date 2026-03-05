"""
Pytest configuration file with shared fixtures.

This module contains fixtures that can be used across multiple test files.
"""

import json
import os
from pathlib import Path

import pytest


@pytest.fixture
def test_dir():
    """Return the path to the tests directory."""
    return Path(__file__).parent


@pytest.fixture
def fixtures_dir(test_dir):
    """Return the path to the fixtures directory."""
    return test_dir / "fixtures"


@pytest.fixture
def mock_credentials_file(fixtures_dir):
    """Create a mock credentials file for testing."""
    credentials = {
        "installed": {
            "client_id": "mock-client-id.apps.googleusercontent.com",
            "project_id": "mock-project-id",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_secret": "mock-client-secret",
            "redirect_uris": ["http://localhost"],
        }
    }

    credentials_path = fixtures_dir / "mock_credentials.json"
    with open(credentials_path, "w") as f:
        json.dump(credentials, f)

    yield credentials_path

    # Clean up after test
    if credentials_path.exists():
        os.remove(credentials_path)


@pytest.fixture
def mock_token_file(fixtures_dir):
    """Create a mock token file for testing."""
    token_data = {
        "token": "mock-token",
        "refresh_token": "mock-refresh-token",
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": "mock-client-id.apps.googleusercontent.com",
        "client_secret": "mock-client-secret",
        "scopes": ["https://www.googleapis.com/auth/gmail.readonly"],
        "expiry": "2025-04-23T00:00:00.000Z",
    }

    token_path = fixtures_dir / "mock_token.json"
    with open(token_path, "w") as f:
        json.dump(token_data, f)

    yield token_path

    # Clean up after test
    if token_path.exists():
        os.remove(token_path)


@pytest.fixture
def mock_env_variables(monkeypatch):
    """Set up mock environment variables for testing."""
    monkeypatch.setenv("CREDENTIALS_DIR", "./tests/fixtures")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "mock_credentials.json")
    monkeypatch.setenv("GMAIL_TOKEN_FILE", "mock_token.json")

    return {
        "CREDENTIALS_DIR": "./tests/fixtures",
        "GOOGLE_APPLICATION_CREDENTIALS": "mock_credentials.json",
        "GMAIL_TOKEN_FILE": "mock_token.json",
    }


@pytest.fixture
def mock_gmail_service(mocker):
    """Create a mock Gmail API service for testing."""
    mock_service = mocker.MagicMock()
    mock_users = mocker.MagicMock()
    mock_messages = mocker.MagicMock()

    # Setup the chain: service.users().messages()
    mock_service.users.return_value = mock_users
    mock_users.messages.return_value = mock_messages

    # Setup profile mock
    mock_profile = mocker.MagicMock()
    mock_profile_response = {
        "emailAddress": "test@example.com",
        "messagesTotal": 100,
        "threadsTotal": 50,
    }
    mock_profile.execute.return_value = mock_profile_response
    mock_users.getProfile.return_value = mock_profile

    return mock_service
