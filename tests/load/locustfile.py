"""
Locust Load Testing Configuration for Blazing Buffalo API.

Usage:
    # Web UI mode
    locust -f tests/load/locustfile.py --host=http://localhost:8000

    # Headless mode
    locust -f tests/load/locustfile.py --host=http://localhost:8000 \
        --users 100 --spawn-rate 10 --run-time 60s --headless

    # Specific scenario
    locust -f tests/load/locustfile.py --host=http://localhost:8000 \
        MistakeAPIUser --users 50 --spawn-rate 5
"""

from locust import HttpUser, task, between, constant, events
import random
import json
from datetime import datetime


class MistakeAPIUser(HttpUser):
    """
    Simulates a typical API user interacting with mistake endpoints.

    Workload distribution:
    - 50% list mistakes (read-heavy)
    - 20% get mistake details
    - 15% search similar mistakes
    - 10% get statistics
    - 5% create mistake
    """

    wait_time = between(1, 3)  # Wait 1-3 seconds between requests

    def on_start(self):
        """Initialize user session."""
        self.mistake_ids = []

    @task(50)
    def list_mistakes(self):
        """List mistakes with pagination."""
        params = {
            "skip": random.randint(0, 100),
            "limit": random.choice([10, 20, 50])
        }
        with self.client.get("/api/v1/mistakes", params=params, catch_response=True) as response:
            if response.status_code == 200:
                data = response.json()
                # Cache some IDs for detail requests
                if data.get("mistakes"):
                    self.mistake_ids = [m["id"] for m in data["mistakes"][:5]]
                response.success()
            else:
                response.failure(f"Got status {response.status_code}")

    @task(20)
    def get_mistake_detail(self):
        """Get details for a specific mistake."""
        if not self.mistake_ids:
            # Fallback to a known ID or skip
            return

        mistake_id = random.choice(self.mistake_ids)
        with self.client.get(f"/api/v1/mistakes/{mistake_id}", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            elif response.status_code == 404:
                # Expected if ID doesn't exist
                response.success()
            else:
                response.failure(f"Got status {response.status_code}")

    @task(15)
    def search_similar(self):
        """Search for similar mistakes."""
        query = random.choice([
            "import error",
            "type error",
            "connection refused",
            "timeout",
            "permission denied"
        ])

        params = {
            "query": query,
            "limit": 5
        }

        with self.client.get("/api/v1/mistakes/similar", params=params, catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Got status {response.status_code}")

    @task(10)
    def get_stats(self):
        """Get system statistics."""
        with self.client.get("/api/v1/stats", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Got status {response.status_code}")

    @task(5)
    def create_mistake(self):
        """Create a new mistake (write operation)."""
        mistake_data = {
            "type": random.choice(["import_error", "type_error", "runtime_error"]),
            "description": f"Load test mistake {random.randint(1000, 9999)}",
            "severity": random.choice(["low", "medium", "high"]),
            "context": {
                "file": "test.py",
                "line": random.randint(1, 500)
            }
        }

        with self.client.post(
            "/api/v1/mistakes",
            json=mistake_data,
            catch_response=True
        ) as response:
            if response.status_code == 201:
                data = response.json()
                if data.get("id"):
                    self.mistake_ids.append(data["id"])
                response.success()
            elif response.status_code == 429:
                # Rate limited - expected
                response.success()
            else:
                response.failure(f"Got status {response.status_code}")


class PlaybookAPIUser(HttpUser):
    """
    Simulates users interacting with playbook endpoints.

    Workload distribution:
    - 60% list playbooks
    - 30% get playbook details
    - 10% execute playbook
    """

    wait_time = between(2, 5)

    def on_start(self):
        """Initialize user session."""
        self.playbook_ids = []

    @task(60)
    def list_playbooks(self):
        """List available playbooks."""
        with self.client.get("/api/v1/playbooks", catch_response=True) as response:
            if response.status_code == 200:
                data = response.json()
                if data.get("playbooks"):
                    self.playbook_ids = [p["id"] for p in data["playbooks"][:5]]
                response.success()
            else:
                response.failure(f"Got status {response.status_code}")

    @task(30)
    def get_playbook_detail(self):
        """Get playbook details."""
        if not self.playbook_ids:
            return

        playbook_id = random.choice(self.playbook_ids)
        with self.client.get(f"/api/v1/playbooks/{playbook_id}", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            elif response.status_code == 404:
                response.success()
            else:
                response.failure(f"Got status {response.status_code}")

    @task(10)
    def execute_playbook(self):
        """Execute a playbook (expensive operation)."""
        if not self.playbook_ids:
            return

        playbook_id = random.choice(self.playbook_ids)
        execution_data = {
            "context": {
                "mistake_id": f"mistake-{random.randint(1, 1000)}",
                "dry_run": True  # Don't actually execute in load test
            }
        }

        with self.client.post(
            f"/api/v1/playbooks/{playbook_id}/execute",
            json=execution_data,
            catch_response=True
        ) as response:
            if response.status_code in [200, 202]:
                response.success()
            elif response.status_code == 429:
                # Rate limited - expected
                response.success()
            else:
                response.failure(f"Got status {response.status_code}")


class HealthCheckUser(HttpUser):
    """
    Simulates health check / monitoring traffic.

    High frequency, low latency operations.
    """

    wait_time = constant(1)  # Every second

    @task
    def health_check(self):
        """Check system health."""
        with self.client.get("/api/v1/health", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Got status {response.status_code}")


class SpikeTrafficUser(HttpUser):
    """
    Simulates spike traffic - burst of requests then idle.

    Used to test autoscaling and rate limiting.
    """

    wait_time = between(0.1, 0.5)  # Very aggressive

    @task(40)
    def burst_list_mistakes(self):
        """Burst read requests."""
        self.client.get("/api/v1/mistakes?limit=100")

    @task(30)
    def burst_stats(self):
        """Burst stats requests."""
        self.client.get("/api/v1/stats")

    @task(20)
    def burst_search(self):
        """Burst search requests."""
        self.client.get("/api/v1/mistakes/similar?query=error&limit=10")

    @task(10)
    def burst_create(self):
        """Burst create requests (will hit rate limit)."""
        self.client.post("/api/v1/mistakes", json={
            "type": "test",
            "description": "spike test"
        })


# Event handlers for custom metrics

@events.request.add_listener
def on_request(request_type, name, response_time, response_length, exception, **kwargs):
    """Track custom metrics per request."""
    if exception:
        print(f"Request failed: {name} - {exception}")


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Log test start."""
    print(f"Load test starting at {datetime.now()}")
    print(f"Target host: {environment.host}")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Log test results."""
    print(f"\nLoad test completed at {datetime.now()}")
    stats = environment.stats

    print("\nRequest Statistics:")
    print(f"  Total requests: {stats.total.num_requests}")
    print(f"  Total failures: {stats.total.num_failures}")
    print(f"  Average response time: {stats.total.avg_response_time:.2f}ms")
    print(f"  Min response time: {stats.total.min_response_time:.2f}ms")
    print(f"  Max response time: {stats.total.max_response_time:.2f}ms")
    print(f"  Requests per second: {stats.total.total_rps:.2f}")

    if stats.total.num_requests > 0:
        failure_rate = (stats.total.num_failures / stats.total.num_requests) * 100
        print(f"  Failure rate: {failure_rate:.2f}%")
