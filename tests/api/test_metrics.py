def test_metrics_endpoint(api_client):
    api_client.get("/health/live")
    api_client.post(
        "/predict",
        json={
            "LIMIT_BAL": 20000.0,
            "SEX": 2,
            "EDUCATION": 2,
            "MARRIAGE": 1,
            "AGE": 24,
            "PAY_0": 2,
            "PAY_2": 2,
            "PAY_3": -1,
            "PAY_4": -1,
            "PAY_5": -2,
            "PAY_6": -2,
            "BILL_AMT1": 3913.0,
            "BILL_AMT2": 3102.0,
            "BILL_AMT3": 689.0,
            "BILL_AMT4": 0.0,
            "BILL_AMT5": 0.0,
            "BILL_AMT6": 0.0,
            "PAY_AMT1": 0.0,
            "PAY_AMT2": 689.0,
            "PAY_AMT3": 0.0,
            "PAY_AMT4": 0.0,
            "PAY_AMT5": 0.0,
            "PAY_AMT6": 0.0,
        },
    )
    response = api_client.get("/metrics")
    assert response.status_code == 200
    text = response.text
    assert "credit_scoring_http_requests_total" in text
    assert "credit_scoring_http_request_latency_seconds" in text
    assert "credit_scoring_inference_requests_total" in text
    assert "credit_scoring_inference_latency_seconds" in text
    assert "credit_scoring_model_ready" in text
    # Drift gauges belong to drift-metrics-exporter only (no fake API zeros).
    assert "ml_data_drift_share" not in text
    assert "ml_data_drift_detected" not in text
    assert "ml_model_roc_auc" not in text
    # No high-cardinality client data labels.
    assert "LIMIT_BAL" not in text
    assert "request_id" not in text
