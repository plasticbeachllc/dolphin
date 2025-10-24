import requests
from tests.utils import wait_for_endpoint


def run_test(base_url):
    """Tests the Git MCP by listing branches."""
    base_endpoint = f"{base_url}/git"
    endpoint = f"{base_endpoint}/git_status"
    wait_for_endpoint(base_endpoint)
    headers = {"Accept": "application/json, text/event-stream"}
    response = requests.post(endpoint, json={'repo_path': ''}, headers=headers)
    data = response.json()
    response.raise_for_status()
    assert isinstance(data, str), "Response should be a string"
    assert "Repository status" in data, "main branch not found in repository"
