from tests.api.conftest import sample_client_payload


def test_predict_success(api_client):
    response = api_client.post("/predict", json=sample_client_payload())
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "probability_default",
        "prediction",
        "model_version",
        "request_id",
    }
    assert 0.0 <= body["probability_default"] <= 1.0
    assert body["prediction"] in (0, 1)
    assert body["model_version"] == "mlp-onnx-fp32-v1"
    assert response.headers.get("X-Request-ID")


def test_predict_503_when_not_ready(not_ready_client):
    response = not_ready_client.post("/predict", json=sample_client_payload())
    assert response.status_code == 503
    assert response.json()["error_code"] == "model_not_ready"


def test_predict_rejects_target_and_id(api_client):
    payload = sample_client_payload()
    payload["ID"] = 1
    response = api_client.post("/predict", json=payload)
    assert response.status_code == 422

    payload = sample_client_payload()
    payload["default.payment.next.month"] = 1
    response = api_client.post("/predict", json=payload)
    assert response.status_code == 422
