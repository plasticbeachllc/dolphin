import time
import requests


def wait_for_endpoint(endpoint_url, timeout=30, interval=1):
    """
    Waits for a specific HTTP endpoint to become available and return a 2xx status.

    Args:
        endpoint_url (str): The full URL of the endpoint to poll.
        timeout (int): The maximum time to wait in seconds.
        interval (float): The time to sleep between polls in seconds.

    Raises:
        TimeoutError: If the endpoint is not available within the timeout period.
    """
    print(f"Waiting for {endpoint_url}...", end="", flush=True)
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            # The /docs endpoint is a reliable indicator that the tool router is up.
            response = requests.get(f"{endpoint_url}/docs", timeout=1)
            print(response.text)
            if response.ok:
                print(" up!")
                return
        except requests.exceptions.RequestException:
            # Ignore connection errors, timeouts, etc. and continue polling.
            pass
        print(".", end="", flush=True)
        time.sleep(interval)

    raise TimeoutError(f"Timed out after {timeout}s waiting for endpoint {endpoint_url}")