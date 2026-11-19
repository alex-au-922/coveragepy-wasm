import httpx


def test_hello(worker_url: str) -> None:
    response = httpx.get(f"{worker_url}/hello", timeout=15)
    assert response.status_code == 200
    assert response.text == "Hello from Workerd!"


def test_unknown_route(worker_url: str) -> None:
    response = httpx.get(f"{worker_url}/missing", timeout=15)
    assert response.status_code == 404
    assert response.text == "Not found"
