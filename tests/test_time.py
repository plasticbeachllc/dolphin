import requests
from tests.utils import wait_for_endpoint

def run_test(base_url):
    """Tests the Time MCP by fetching the current time."""
    base_endpoint = f"{base_url}/time"
    endpoint = f"{base_endpoint}/get_current_time"
    wait_for_endpoint(base_endpoint)
    headers = {"Accept": "application/json, text/event-stream"}
    # This endpoint doesn't require a body, so we send None.
    response = requests.post(endpoint, json={'timezone': 'America/Los_Angeles'}, headers=headers)
    response.raise_for_status()
    data = response.json()
    assert "timezone" in data, "Response JSON must contain 'timezone' key"
    assert isinstance(data["timezone"], str), "The 'timezone' value should be a string."
