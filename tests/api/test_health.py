def test_live_always_ok(api_client):
    response = api_client.get("/health/live")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_ready_ok_when_model_loaded(api_client):
    response = api_client.get("/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["model_loaded"] is True


def test_ready_503_when_not_ready(not_ready_client):
    response = not_ready_client.get("/health/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["error_code"] == "model_not_ready"
    assert "request_id" in body
    assert "traceback" not in body["message"].lower()


def test_model_info(api_client):
    response = api_client.get("/model/info")
    assert response.status_code == 200
    body = response.json()
    assert body["backend"] == "onnx"
    assert body["model_format"] == "onnx-fp32"
    assert body["threshold"] == 0.5
    assert "MODEL_PATH" not in str(body)
    assert "/app/" not in str(body)
