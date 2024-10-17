import pytest
from fastapi import HTTPException
from pydantic import ValidationError

import app.schemas as test_module

from tests.utils import NEXUS_BUCKET, NEXUS_ENDPOINT, NEXUS_TOKEN


def test_nexus_config():
    result = test_module.NexusConfig(
        endpoint=NEXUS_ENDPOINT,
        bucket=NEXUS_BUCKET,
        token=NEXUS_TOKEN,
    )
    assert isinstance(result, test_module.NexusConfig)
    assert result.token == NEXUS_TOKEN


def test_nexus_config_raises_with_invalid_endpoint():
    with pytest.raises(ValidationError, match="Nexus endpoint is invalid"):
        test_module.NexusConfig(
            endpoint="https://fake-endpoint",
            bucket=NEXUS_BUCKET,
            token=NEXUS_TOKEN,
        )


def test_nexus_config_raises_with_invalid_bucket():
    with pytest.raises(ValidationError, match="Nexus bucket is invalid"):
        test_module.NexusConfig(
            endpoint=NEXUS_ENDPOINT,
            bucket="bbp/fake-bucket",
            token=NEXUS_TOKEN,
        )


def test_nexus_config_from_params():
    result = test_module.NexusConfig.from_headers(
        nexus_endpoint=NEXUS_ENDPOINT,
        nexus_bucket=NEXUS_BUCKET,
        nexus_token=NEXUS_TOKEN,
    )
    assert isinstance(result, test_module.NexusConfig)
    assert result.token == NEXUS_TOKEN


def test_nexus_config_from_params_raises_with_invalid_endpoint():
    with pytest.raises(HTTPException, match="Nexus endpoint is invalid"):
        test_module.NexusConfig.from_headers(
            nexus_endpoint="https://fake-endpoint",
            nexus_bucket=NEXUS_BUCKET,
            nexus_token=NEXUS_TOKEN,
        )


def test_nexus_config_from_params_raises_with_invalid_bucket():
    with pytest.raises(HTTPException, match="Nexus bucket is invalid"):
        test_module.NexusConfig.from_headers(
            nexus_endpoint=NEXUS_ENDPOINT,
            nexus_bucket="bbp/fake-bucket",
            nexus_token=NEXUS_TOKEN,
        )


def test_circuit_ref_from_id():
    result = test_module.CircuitRef(id="test-id", path=None)
    assert isinstance(result, test_module.CircuitRef)

    result = test_module.CircuitRef.from_params(circuit_id="test-id")
    assert isinstance(result, test_module.CircuitRef)


def test_circuit_ref_from_path(input_path):
    result = test_module.CircuitRef(id=None, path=input_path)
    assert isinstance(result, test_module.CircuitRef)


def test_circuit_ref_raises_with_none():
    with pytest.raises(ValidationError, match="circuit id or path must be specified"):
        test_module.CircuitRef(id=None, path=None)


def test_circuit_ref_raises_with_both(input_path):
    with pytest.raises(
        ValidationError, match="circuit id and path cannot be specified at the same time"
    ):
        test_module.CircuitRef(id="test-id", path=input_path)


def test_circuit_ref_raises_with_wrong_extension():
    with pytest.raises(ValidationError, match="Path invalid because of the extension"):
        test_module.CircuitRef(id=None, path="/path/to/nodes.h5")


def test_circuit_ref_raises_with_non_existent_path():
    with pytest.raises(ValidationError, match="Path invalid because non existent"):
        test_module.CircuitRef(id=None, path="/path/to/non/existent/circuit_config.json")
