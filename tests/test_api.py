"""
SmartScrape Pro — Test Suite
Tests for auth, jobs, payments, and admin APIs
"""
import pytest
import asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from main import app
from backend.models.database import get_db
from backend.models.models import Base


# ──────────────────────────────────────────
# TEST DATABASE SETUP
# ──────────────────────────────────────────

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestSessionLocal = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


async def override_get_db():
    async with TestSessionLocal() as session:
        yield session


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session", autouse=True)
async def setup_db():
    """Create test database tables."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture(scope="session")
async def client():
    """Create async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ──────────────────────────────────────────
# AUTH TESTS
# ──────────────────────────────────────────

class TestAuthentication:

    @pytest.mark.asyncio
    async def test_signup_success(self, client):
        """Test successful user registration."""
        response = await client.post("/api/v1/auth/signup", json={
            "email": "test@smartscrapepro.com",
            "username": "testuser",
            "password": "TestPass123",
            "full_name": "Test User",
        })
        assert response.status_code == 201
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["email"] == "test@smartscrapepro.com"
        assert data["plan"] == "free"
        TestAuthentication.token = data["access_token"]

    @pytest.mark.asyncio
    async def test_signup_duplicate_email(self, client):
        """Test signup with duplicate email returns 409."""
        response = await client.post("/api/v1/auth/signup", json={
            "email": "test@smartscrapepro.com",
            "username": "anotheruser",
            "password": "TestPass123",
        })
        assert response.status_code == 409
        assert "already registered" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_signup_weak_password(self, client):
        """Test signup with weak password is rejected."""
        response = await client.post("/api/v1/auth/signup", json={
            "email": "weak@test.com",
            "username": "weakuser",
            "password": "short",
        })
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_login_success(self, client):
        """Test successful login returns tokens."""
        response = await client.post("/api/v1/auth/login", json={
            "email": "test@smartscrapepro.com",
            "password": "TestPass123",
        })
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["role"] in ["standard", "admin", "premium"]

    @pytest.mark.asyncio
    async def test_login_wrong_password(self, client):
        """Test login with wrong password returns 401."""
        response = await client.post("/api/v1/auth/login", json={
            "email": "test@smartscrapepro.com",
            "password": "WrongPassword!",
        })
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_me_authenticated(self, client):
        """Test /auth/me with valid token."""
        # First login to get token
        login_res = await client.post("/api/v1/auth/login", json={
            "email": "test@smartscrapepro.com",
            "password": "TestPass123",
        })
        token = login_res.json()["access_token"]

        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "test@smartscrapepro.com"
        assert "subscription" in data

    @pytest.mark.asyncio
    async def test_get_me_unauthenticated(self, client):
        """Test /auth/me without token returns 401/403."""
        response = await client.get("/api/v1/auth/me")
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_refresh_token(self, client):
        """Test token refresh flow."""
        login_res = await client.post("/api/v1/auth/login", json={
            "email": "test@smartscrapepro.com",
            "password": "TestPass123",
        })
        refresh_token = login_res.json()["refresh_token"]

        response = await client.post("/api/v1/auth/refresh", json={
            "refresh_token": refresh_token
        })
        assert response.status_code == 200
        assert "access_token" in response.json()


# ──────────────────────────────────────────
# JOB TESTS
# ──────────────────────────────────────────

class TestScrapingJobs:

    @pytest.fixture(autouse=True)
    async def get_token(self, client):
        """Get auth token for each test."""
        # Create second test user (avoid job limit issues)
        await client.post("/api/v1/auth/signup", json={
            "email": "jobtest@smartscrapepro.com",
            "username": "jobuser",
            "password": "TestPass123",
        })
        login_res = await client.post("/api/v1/auth/login", json={
            "email": "jobtest@smartscrapepro.com",
            "password": "TestPass123",
        })
        self.token = login_res.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}

    @pytest.mark.asyncio
    async def test_create_job(self, client):
        """Test creating a scraping job."""
        response = await client.post("/api/v1/jobs/", json={
            "name": "Test Scraping Job",
            "target_url": "https://example.com",
            "engine": "beautifulsoup",
            "export_format": "json",
        }, headers=self.headers)
        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        assert data["name"] == "Test Scraping Job"
        assert data["status"] == "pending"
        self.__class__.job_id = data["id"]

    @pytest.mark.asyncio
    async def test_list_jobs(self, client):
        """Test listing user's jobs."""
        response = await client.get("/api/v1/jobs/", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert "jobs" in data
        assert "total" in data
        assert isinstance(data["jobs"], list)

    @pytest.mark.asyncio
    async def test_get_job_detail(self, client):
        """Test getting single job detail."""
        if not hasattr(self.__class__, 'job_id'):
            pytest.skip("No job created yet")

        response = await client.get(
            f"/api/v1/jobs/{self.__class__.job_id}",
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == self.__class__.job_id
        assert "logs" in data

    @pytest.mark.asyncio
    async def test_job_tenant_isolation(self, client):
        """Test that user cannot access another user's job."""
        # Create a different user
        await client.post("/api/v1/auth/signup", json={
            "email": "other@test.com",
            "username": "otheruser99",
            "password": "TestPass123",
        })
        other_login = await client.post("/api/v1/auth/login", json={
            "email": "other@test.com", "password": "TestPass123"
        })
        other_token = other_login.json()["access_token"]

        if not hasattr(self.__class__, 'job_id'):
            pytest.skip("No job created")

        # Other user tries to access first user's job
        response = await client.get(
            f"/api/v1/jobs/{self.__class__.job_id}",
            headers={"Authorization": f"Bearer {other_token}"}
        )
        assert response.status_code == 404  # Should not find it

    @pytest.mark.asyncio
    async def test_update_job(self, client):
        """Test updating a job."""
        if not hasattr(self.__class__, 'job_id'):
            pytest.skip("No job created")

        response = await client.put(
            f"/api/v1/jobs/{self.__class__.job_id}",
            json={"name": "Updated Job Name"},
            headers=self.headers
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_delete_job(self, client):
        """Test deleting a job."""
        # Create a job to delete
        create_res = await client.post("/api/v1/jobs/", json={
            "name": "Job to Delete",
            "target_url": "https://example.com",
        }, headers=self.headers)
        job_id = create_res.json()["id"]

        response = await client.delete(
            f"/api/v1/jobs/{job_id}",
            headers=self.headers
        )
        assert response.status_code == 200

        # Verify deleted
        get_res = await client.get(f"/api/v1/jobs/{job_id}", headers=self.headers)
        assert get_res.status_code == 404

    @pytest.mark.asyncio
    async def test_invalid_engine(self, client):
        """Test creating job with invalid engine is rejected."""
        response = await client.post("/api/v1/jobs/", json={
            "name": "Bad Job",
            "target_url": "https://example.com",
            "engine": "invalid_engine_xyz",
        }, headers=self.headers)
        assert response.status_code == 400


# ──────────────────────────────────────────
# PAYMENT TESTS
# ──────────────────────────────────────────

class TestPayments:

    @pytest.fixture(autouse=True)
    async def get_token(self, client):
        login_res = await client.post("/api/v1/auth/login", json={
            "email": "test@smartscrapepro.com",
            "password": "TestPass123",
        })
        self.token = login_res.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}

    @pytest.mark.asyncio
    async def test_get_plans(self, client):
        """Test getting available plans (public endpoint)."""
        response = await client.get("/api/v1/payments/plans")
        assert response.status_code == 200
        plans = response.json()
        assert len(plans) >= 4
        plan_ids = [p["id"] for p in plans]
        assert "free" in plan_ids
        assert "basic" in plan_ids
        assert "pro" in plan_ids
        assert "business" in plan_ids

    @pytest.mark.asyncio
    async def test_get_subscription(self, client):
        """Test getting current subscription."""
        response = await client.get(
            "/api/v1/payments/subscription",
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "plan" in data
        assert "jobs_limit" in data

    @pytest.mark.asyncio
    async def test_payment_history(self, client):
        """Test getting payment history."""
        response = await client.get(
            "/api/v1/payments/history",
            headers=self.headers
        )
        assert response.status_code == 200
        assert isinstance(response.json(), list)


# ──────────────────────────────────────────
# HEALTH & SYSTEM TESTS
# ──────────────────────────────────────────

class TestSystem:

    @pytest.mark.asyncio
    async def test_health_check(self, client):
        """Test health endpoint returns 200."""
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data

    @pytest.mark.asyncio
    async def test_root(self, client):
        """Test root endpoint."""
        response = await client.get("/")
        assert response.status_code == 200
        assert "platform" in response.json()

    @pytest.mark.asyncio
    async def test_docs_accessible(self, client):
        """Test API docs are accessible."""
        response = await client.get("/api/docs")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_admin_requires_auth(self, client):
        """Test admin endpoints reject non-admins."""
        # Without token
        response = await client.get("/api/v1/admin/stats")
        assert response.status_code in [401, 403]

        # With regular user token
        login_res = await client.post("/api/v1/auth/login", json={
            "email": "test@smartscrapepro.com",
            "password": "TestPass123",
        })
        token = login_res.json()["access_token"]
        response = await client.get(
            "/api/v1/admin/stats",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 403
