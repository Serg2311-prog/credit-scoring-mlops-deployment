from tests.api.conftest import sample_client_payload


def test_batch_success_and_order(api_client):
    items = [
        sample_client_payload(AGE=20),
        sample_client_payload(AGE=80),
        sample_client_payload(AGE=40),
    ]
    response = api_client.post("/predict/batch", json={"items": items})
    assert response.status_code == 200
    body = response.json()
    assert body["batch_size"] == 3
    assert len(body["results"]) == 3
    probs = [row["probability_default"] for row in body["results"]]
    assert probs == [0.2, 0.8, 0.4]


def test_batch_empty_rejected(api_client):
    response = api_client.post("/predict/batch", json={"items": []})
    assert response.status_code == 422


def test_batch_limit(api_client, monkeypatch):
    from src.api.settings import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("MAX_BATCH_SIZE", "2")
    get_settings.cache_clear()
    items = [sample_client_payload(AGE=21 + i) for i in range(3)]
    response = api_client.post("/predict/batch", json={"items": items})
    assert response.status_code == 422
    assert response.json()["error_code"] == "batch_limit_exceeded"
    get_settings.cache_clear()
