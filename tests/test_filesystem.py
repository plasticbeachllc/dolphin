import requests
from tests.utils import wait_for_endpoint

def run_test(base_url):
    """Tests the Filesystem MCP by listing a directory."""
    base_endpoint = f"{base_url}/filesystem"
    endpoint = f"{base_endpoint}/list_directory"
    wait_for_endpoint(base_endpoint)
    payload = {"path": "/worktable/dolphin"}
    headers = {"Accept": "application/json, text/event-stream"}
    response = requests.post(endpoint, json=payload, headers=headers)
    print(response.text)
    response.raise_for_status()  # Fails on 4xx or 5xx status codes
    data = response.json()
    assert "[FILE] README.md" in data, "README.md file not found in directory listing"
