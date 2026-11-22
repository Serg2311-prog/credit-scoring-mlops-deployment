from tests.api.conftest import sample_client_payload


def test_missing_required_field(api_client):
    payload = sample_client_payload()
    del payload["LIMIT_BAL"]
    response = api_client.post("/predict", json=payload)
    assert response.status_code == 422


def test_wrong_type(api_client):
    payload = sample_client_payload(AGE="old")
    response = api_client.post("/predict", json=payload)
    assert response.status_code == 422


def test_nan_and_infinity_rejected_by_schema():
    import pytest
    from pydantic import ValidationError

    from src.api.schemas import ClientFeatures

    with pytest.raises(ValidationError):
        ClientFeatures(**sample_client_payload(LIMIT_BAL=float("nan")))
    with pytest.raises(ValidationError):
        ClientFeatures(**sample_client_payload(BILL_AMT1=float("inf")))


def test_invalid_category_and_range(api_client):
    response = api_client.post("/predict", json=sample_client_payload(SEX=9))
    assert response.status_code == 422
    response = api_client.post("/predict", json=sample_client_payload(AGE=200))
    assert response.status_code == 422
    response = api_client.post("/predict", json=sample_client_payload(EDUCATION=9))
    assert response.status_code == 422
    response = api_client.post("/predict", json=sample_client_payload(PAY_AMT1=-1))
    assert response.status_code == 422


def test_extra_field_forbidden(api_client):
    payload = sample_client_payload()
    payload["EXTRA"] = 1
    response = api_client.post("/predict", json=payload)
    assert response.status_code == 422
