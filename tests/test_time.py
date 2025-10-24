import requests
from tests.utils import wait_for_endpoint

def run_test(base_url):
    """Tests the Time MCP by fetching the current time."""
    base_endpoint = f"{base_url}/time"
    endpoint = f"{base_endpoint}/get"
    wait_for_endpoint(base_endpoint)
    headers = {"Accept": "application/json, text/event-stream"}
    response = requests.post(endpoint, json={}, headers=headers)
    response.raise_for_status()
    data = response.json()
    assert "iso" in data, "Response JSON must contain 'iso' key"
