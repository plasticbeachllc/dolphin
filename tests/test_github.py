import requests
from tests.utils import wait_for_endpoint


def run_test(base_url):
    """Tests the Git MCP by listing branches."""
    base_endpoint = f"{base_url}/git"
    endpoint = f"{base_endpoint}/list_branches"
    wait_for_endpoint(base_endpoint)
    headers = {"Accept": "application/json, text/event-stream"}
    response = requests.post(endpoint, json={"path": "dolphin"}, headers=headers)
    response.raise_for_status()
    data = response.json()
    assert isinstance(data, list), "Response should be a list of branches"
    assert "main" in data, "main branch not found in repository"
