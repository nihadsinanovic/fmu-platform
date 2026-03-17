"""Tests for project API endpoints.

These tests require a running database. For CI, use a test database
or mock the database dependency.
"""

# Placeholder for API tests — requires database setup
# Example structure using httpx + pytest-asyncio:
#
# import pytest
# from httpx import ASGITransport, AsyncClient
# from app.main import app
#
# @pytest.fixture
# async def client():
#     async with AsyncClient(
#         transport=ASGITransport(app=app), base_url="http://test"
#     ) as ac:
#         yield ac
#
# class TestProjectsAPI:
#     async def test_create_project(self, client):
#         response = await client.post("/api/projects", json={"name": "Test"})
#         assert response.status_code == 201
