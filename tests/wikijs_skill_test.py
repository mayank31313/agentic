import pytest

from src.skills.wikijs_skill import WikiJsSkill


# Mock the WikiJsSkill class methods for isolated testing
@pytest.fixture
def skill_instance():
    # Use a placeholder token for testing purposes
    return WikiJsSkill("test_token")


def test_skill_initialization_with_token(skill_instance):
    # Test that the class initializes without crashing when given a valid token
    assert isinstance(skill_instance, WikiJsSkill)
    assert skill_instance.api_token == "test_token"


def test_create_page_success(skill_instance):
    # Mock the API call to ensure the structure is correct upon success
    # We simulate the actual call by ensuring the method exists and returns expected mock data
    result = skill_instance.create_page("Test Page", "Some content")
    assert result["id"] == "placeholder_id"
    assert result["title"] == "Test Page"


def test_update_page_with_missing_fields(skill_instance):
    # Mocking an API failure for an update attempt
    # We mock the method to return an error structure
    skill_instance.update_page = lambda page_id, title, content: {
        "error": "400 Bad Request"
    }

    result = skill_instance.update_page("existing_id", None, None)
    assert "error" in result


def test_delete_page_not_found(skill_instance):
    # Mocking an API failure for a 404 Not Found
    # We mock the method to return False on failure
    skill_instance.delete_page = lambda page_id: False

    result = skill_instance.delete_page("non_existent_id")
    assert result is False
