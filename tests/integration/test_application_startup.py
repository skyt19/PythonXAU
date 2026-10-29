"""
Integration tests for application startup and basic endpoints.

These tests verify that the FastAPI application starts correctly
and responds to basic HTTP requests.
"""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create a test client for the FastAPI application."""
    from app.main import app
    return TestClient(app)


class TestApplicationStartup:
    """Test application startup and initialization."""

    def test_app_imports_successfully(self):
        """Verify the application module imports without errors."""
        from app import main
        assert main is not None
        assert hasattr(main, 'app')

    def test_app_has_correct_metadata(self, client):
        """Verify application metadata is correct."""
        from app.main import app
        assert app.title == "XAUUSD AI Farming HQ"
        assert app.version == "1.0.0"
        assert "Demo" in app.description or "DEMO" in app.description

    def test_root_endpoint(self, client):
        """Test root endpoint returns correct information."""
        response = client.get("/")
        assert response.status_code == 200

        data = response.json()
        assert data["service"] == "XAUUSD AI Farming HQ"
        assert data["version"] == "1.0.0"
        assert data["status"] == "operational"
        assert data["demo_only"] is True

    def test_health_endpoint(self, client):
        """Test health endpoint returns healthy status."""
        response = client.get("/health")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "farming_hq"
        assert data["demo_only"] is True

    def test_status_endpoint(self, client):
        """Test detailed status endpoint."""
        response = client.get("/status")
        assert response.status_code == 200

        data = response.json()
        assert data["service"] == "XAUUSD AI Farming HQ"
        assert data["version"] == "1.0.0"
        assert data["demo_only"] is True
        assert "configuration" in data
        assert "database" in data
        assert "execution" in data
        assert "components" in data

        # Verify execution is disabled
        assert data["execution"]["enabled"] is False

    def test_demo_only_enforced(self, client):
        """CRITICAL: Verify DEMO_ONLY is enforced."""
        response = client.get("/")
        data = response.json()
        assert data["demo_only"] is True, "DEMO_ONLY must be True"


class TestDashboardAPI:
    """Test dashboard API endpoints."""

    def test_api_info_endpoint(self, client):
        """Test /api/v1/info endpoint."""
        response = client.get("/api/v1/info")
        assert response.status_code == 200

        data = response.json()
        assert data["name"] == "XAUUSD AI Farming HQ"
        assert data["demo_only"] is True
        assert data["symbol"] == "XAUUSD"
        assert data["timeframe"] == "M15"

    def test_api_config_endpoint(self, client):
        """Test /api/v1/config endpoint."""
        response = client.get("/api/v1/config")
        assert response.status_code == 200

        data = response.json()
        assert "trading" in data
        assert "risk" in data
        assert "model" in data
        assert "execution" in data

        # Verify execution is disabled
        assert data["execution"]["enabled"] is False

    def test_api_system_state_endpoint(self, client):
        """Test /api/v1/system/state endpoint."""
        response = client.get("/api/v1/system/state")
        assert response.status_code == 200

        data = response.json()
        assert "execution_enabled" in data
        assert "daily_realized_pnl" in data

        # Execution must be disabled
        assert data["execution_enabled"] is False

    def test_api_account_status_endpoint(self, client):
        """Test /api/v1/account/status endpoint."""
        response = client.get("/api/v1/account/status")
        assert response.status_code == 200

        data = response.json()
        assert "connected" in data
        assert "demo_only_enforced" in data
        assert data["demo_only_enforced"] is True

    def test_api_market_status_endpoint(self, client):
        """Test /api/v1/market/status endpoint."""
        response = client.get("/api/v1/market/status")
        assert response.status_code == 200

        data = response.json()
        assert data["symbol"] == "XAUUSD"
        assert data["timeframe"] == "M15"

    def test_api_statistics_endpoint(self, client):
        """Test /api/v1/statistics endpoint."""
        response = client.get("/api/v1/statistics")
        assert response.status_code == 200

        data = response.json()
        assert "data" in data
        assert "predictions" in data
        assert "signals" in data
        assert "trades" in data
        assert "models" in data


class TestDatabaseInitialization:
    """Test database initialization during startup."""

    def test_database_tables_created(self, client):
        """Verify database tables are created during startup."""
        # Access an endpoint that uses the database
        response = client.get("/api/v1/system/state")
        assert response.status_code == 200

        # If we get here, database was initialized successfully

    def test_system_state_initialized(self, client):
        """Verify SystemState is created if it doesn't exist."""
        response = client.get("/api/v1/system/state")
        assert response.status_code == 200

        data = response.json()
        # Should return valid state even if it was just created
        assert "execution_enabled" in data
        assert isinstance(data["execution_enabled"], bool)


class TestSafetyConstraints:
    """Test safety constraints are enforced."""

    def test_localhost_binding(self):
        """Verify application is configured to bind to localhost."""
        from app.config import config
        assert config.dashboard_host in ["127.0.0.1", "localhost", "::1"]

    def test_execution_disabled_by_default(self, client):
        """CRITICAL: Verify execution is disabled by default."""
        response = client.get("/status")
        data = response.json()
        assert data["execution"]["enabled"] is False

    def test_no_execution_module_loaded(self, client):
        """Verify no execution module is loaded in Phase 1."""
        response = client.get("/status")
        data = response.json()

        components = data["components"]
        assert components["strategy"] == "not_loaded"
        assert components["risk_manager"] == "not_loaded"


class TestAPIDocumentation:
    """Test API documentation is available."""

    def test_openapi_schema_available(self, client):
        """Verify OpenAPI schema is accessible."""
        response = client.get("/openapi.json")
        assert response.status_code == 200

        schema = response.json()
        assert "openapi" in schema
        assert "info" in schema
        assert "paths" in schema

    def test_docs_endpoint_available(self, client):
        """Verify Swagger docs are accessible."""
        response = client.get("/docs")
        assert response.status_code == 200

    def test_redoc_endpoint_available(self, client):
        """Verify ReDoc is accessible."""
        response = client.get("/redoc")
        assert response.status_code == 200
