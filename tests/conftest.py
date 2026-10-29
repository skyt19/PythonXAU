"""
Pytest configuration and shared fixtures.
"""
import os
import sys
from pathlib import Path

import pytest

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Set test environment variables
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["LOG_LEVEL"] = "WARNING"
os.environ["DEMO_ONLY"] = "true"


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Set up test environment before any tests run."""
    # Ensure test database is in memory
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"


@pytest.fixture(scope="session")
def test_database_url():
    """Provide in-memory database URL for tests."""
    return "sqlite:///:memory:"


@pytest.fixture(scope="function")
def clean_database():
    """Provide a clean database for each test."""
    from app.database import DatabaseManager, Base

    db_manager = DatabaseManager("sqlite:///:memory:")
    db_manager.create_tables()

    yield db_manager

    # Cleanup
    Base.metadata.drop_all(bind=db_manager.engine)
    db_manager.close()
