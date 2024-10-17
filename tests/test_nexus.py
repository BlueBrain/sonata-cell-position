import logging
from pathlib import Path
from unittest.mock import MagicMock

import jwt
import pytest
import requests
import voxcell
from requests import HTTPError

import app.nexus as test_module
from app.errors import ClientError

from tests.utils import assert_cache, clear_cache


@pytest.fixture
def nexus_acl():
    return {
        "@context": [
            "https://bluebrain.github.io/nexus/contexts/metadata.json",
            "https://bluebrain.github.io/nexus/contexts/search.json",
            "https://bluebrain.github.io/nexus/contexts/acls.json",
        ],
        "_total": 1,
        "_results": [
            {
                "@id": "https://bbp.epfl.ch/nexus/v1/acls/bbp/mmb-point-neuron-framework-model",
                "@type": "AccessControlList",
                "acl": [
                    {
                        "identity": {
                            "@id": "https://bbp.epfl.ch/nexus/v1/realms/bbp/groups/bbp-staff",
                            "@type": "Group",
                            "group": "/bbp-staff",
                            "realm": "bbp",
                        },
                        "permissions": [
                            "projects/read",
                            "views/query",
                            "gpfs-proj134/read",
                            "resources/read",
                            "gpfs-proj134/write",
                            "resources/write",
                            "files/write",
                            "events/read",
                        ],
                    },
                    {
                        "identity": {
                            "@id": "https://bbp.epfl.ch/nexus/v1/realms/bbp/groups/bbp-dev-proj134",
                            "@type": "Group",
                            "group": "/bbp-dev-proj134",
                            "realm": "bbp",
                        },
                        "permissions": [
                            "archives/write",
                            "views/query",
                            "gpfs-proj134/read",
                            "resources/read",
                            "views/write",
                            "gpfs-proj134/write",
                            "resources/write",
                            "files/write",
                            "events/read",
                        ],
                    },
                ],
                "_constrainedBy": "https://bluebrain.github.io/nexus/schemas/acls.json",
                "_createdAt": "2022-05-24T09:02:25.905Z",
                "_createdBy": "https://bbp.epfl.ch/nexus/v1/realms/serviceaccounts/users/username",
                "_deprecated": False,
                "_path": "/bbp/mmb-point-neuron-framework-model",
                "_rev": 13,
                "_self": "https://bbp.epfl.ch/nexus/v1/acls/bbp/mmb-point-neuron-framework-model",
                "_updatedAt": "2023-10-26T13:14:06.126Z",
                "_updatedBy": "https://bbp.epfl.ch/nexus/v1/realms/bbp/users/username",
            }
        ],
    }


@pytest.fixture
def nexus_token():
    return jwt.encode(
        {
            "exp": 1706709167,
            "iat": 1706705567,
            "jti": "00000000-0000-0000-0000-000000000000",
            "iss": "https://bbpauth.epfl.ch/auth/realms/BBP",
            "aud": "coreservices-kubernetes",
            "sub": "f:00000000-0000-0000-0000-000000000000:testuser",
            "typ": "Bearer",
            "azp": "bbp-workflow",
            "session_state": "00000000-0000-0000-0000-000000000000",
            "allowed-origins": ["*"],
            "realm_access": {"roles": ["offline_access"]},
            "scope": "profile offline_access openid groups email",
            "sid": "00000000-0000-0000-0000-000000000000",
            "email_verified": True,
            "name": "Test User",
            "preferred_username": "testuser",
            "given_name": "Test",
            "family_name": "User",
            "email": "test.user@example.org",
        },
        key="",
    )


def test_load_cached_resource(nexus_config):
    resource_id = "test-resource-id"
    resource = MagicMock()
    resource_class = MagicMock()
    resource_class.__name__ = "ResourceMock"
    resource_class.from_id.return_value = resource

    with clear_cache(test_module.load_cached_resource) as tested_func:
        result = tested_func(resource_class, resource_id, nexus_config=nexus_config)
        assert_cache(tested_func, hits=0, misses=1, currsize=1)
        assert result is resource
        assert resource_class.from_id.call_count == 1

        result = tested_func(resource_class, resource_id, nexus_config=nexus_config)
        assert_cache(tested_func, hits=1, misses=1, currsize=1)
        assert result is resource
        assert resource_class.from_id.call_count == 1


def test_load_cached_resource_with_nexus_error(nexus_config):
    resource_id = "test-resource-id"
    resource_class = MagicMock()
    resource_class.__name__ = "ResourceMock"
    resource_class.from_id.side_effect = HTTPError(
        "401 Client Error: Unauthorized for url",
        response=MagicMock(status_code=401),
    )

    with clear_cache(test_module.load_cached_resource) as tested_func:
        with pytest.raises(ClientError, match="401 Client Error: Unauthorized for url"):
            tested_func(resource_class, resource_id, nexus_config=nexus_config)
        assert_cache(tested_func, hits=0, misses=1, currsize=0)


def test_load_cached_resource_with_resource_id_none(nexus_config):
    resource_id = None
    resource_class = MagicMock()
    resource_class.__name__ = "ResourceMock"
    resource_class.from_id.side_effect = HTTPError(
        "401 Client Error: Unauthorized for url",
        response=MagicMock(status_code=401),
    )

    with clear_cache(test_module.load_cached_resource) as tested_func:
        with pytest.raises(ClientError, match="Resource id must be set"):
            tested_func(resource_class, resource_id, nexus_config=nexus_config)
        assert_cache(tested_func, hits=0, misses=1, currsize=0)


def test_load_cached_resource_with_result_none(nexus_config):
    resource_id = "test-resource-id"
    resource_class = MagicMock()
    resource_class.__name__ = "ResourceMock"
    resource_class.from_id.return_value = None

    with clear_cache(test_module.load_cached_resource) as tested_func:
        with pytest.raises(ClientError, match="Resource not found"):
            tested_func(resource_class, resource_id, nexus_config=nexus_config)
        assert_cache(tested_func, hits=0, misses=1, currsize=0)


def test_load_cached_region_map(nexus_config, hierarchy):
    resource = MagicMock()
    resource.distribution = [
        MagicMock(encodingFormat="application/ld+json"),
        MagicMock(encodingFormat="application/json", download=MagicMock(return_value=hierarchy)),
    ]

    with clear_cache(test_module.load_cached_region_map) as tested_func:
        result_1 = tested_func(resource, nexus_config=nexus_config)
        assert_cache(tested_func, hits=0, misses=1, currsize=1)
        assert isinstance(result_1, voxcell.RegionMap)
        assert resource.distribution[0].download.call_count == 0
        assert resource.distribution[1].download.call_count == 1

        result_2 = tested_func(resource, nexus_config=nexus_config)
        assert_cache(tested_func, hits=1, misses=1, currsize=1)
        assert isinstance(result_2, voxcell.RegionMap)
        assert resource.distribution[0].download.call_count == 0
        assert resource.distribution[1].download.call_count == 1

        assert result_1 is result_2


def test_load_cached_region_map_hierarchy_not_found(nexus_config):
    resource = MagicMock()
    resource.distribution = [
        MagicMock(encodingFormat="application/ld+json"),
    ]

    with clear_cache(test_module.load_cached_region_map) as tested_func:
        with pytest.raises(ClientError, match="Hierarchy json not found for id"):
            tested_func(resource, nexus_config=nexus_config)
        assert_cache(tested_func, hits=0, misses=1, currsize=0)
        assert resource.distribution[0].download.call_count == 0


def test_load_cached_alternative_region_map(nexus_config, alternative_brain_region_file):
    resource = MagicMock()
    resource.distribution = [
        MagicMock(encodingFormat="text/turtle"),
        MagicMock(
            encodingFormat="application/ld+json",
            download=MagicMock(return_value=alternative_brain_region_file),
        ),
        MagicMock(encodingFormat="text/csv"),
    ]

    with clear_cache(test_module.load_cached_alternative_region_map) as tested_func:
        result_1 = tested_func(resource, nexus_config=nexus_config)
        assert_cache(tested_func, hits=0, misses=1, currsize=1)
        assert isinstance(result_1, dict)
        assert resource.distribution[0].download.call_count == 0
        assert resource.distribution[1].download.call_count == 1

        result_2 = tested_func(resource, nexus_config=nexus_config)
        assert_cache(tested_func, hits=1, misses=1, currsize=1)
        assert isinstance(result_2, dict)
        assert resource.distribution[0].download.call_count == 0
        assert resource.distribution[1].download.call_count == 1

        assert result_1 is result_2


def test_load_cached_alternative_region_map_hierarchy_not_found(nexus_config):
    resource = MagicMock()
    resource.distribution = [
        MagicMock(encodingFormat="application/json"),
    ]

    with clear_cache(test_module.load_cached_alternative_region_map) as tested_func:
        with pytest.raises(ClientError, match="Alternative hierarchy json not found for id"):
            tested_func(resource, nexus_config=nexus_config)
        assert_cache(tested_func, hits=0, misses=1, currsize=0)
        assert resource.distribution[0].download.call_count == 0


def test_get_circuit_config_path():
    path = "/path/to/circuit_config.json"
    resource = MagicMock()
    resource.circuitConfigPath.get_url_as_path.return_value = path

    result = test_module.get_circuit_config_path(resource)
    assert result == Path(path)


def test_get_circuit_config_path_with_missing_attribute():
    resource = MagicMock()
    resource.circuitConfigPath = None

    with pytest.raises(
        ClientError, match="Error in resource.*object has no attribute 'get_url_as_path'"
    ):
        test_module.get_circuit_config_path(resource)


def test_is_user_authorized_true(nexus_config, nexus_acl, nexus_token, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    mock_response = MagicMock()
    mock_response.json.return_value = nexus_acl
    mock_get = MagicMock(return_value=mock_response)
    monkeypatch.setattr(test_module.requests, "get", mock_get)
    nexus_config.token = nexus_token

    result = test_module.is_user_authorized(nexus_config)

    assert result == 200
    assert "User testuser [Test User] authorized" in caplog.text
    assert mock_get.call_count == 1


def test_is_user_authorized_false_because_of_permissions(
    nexus_config, nexus_acl, nexus_token, monkeypatch, caplog
):
    caplog.set_level(logging.INFO)
    nexus_acl["_results"][0]["acl"][0]["permissions"] = ["projects/read"]
    nexus_acl["_results"][0]["acl"][1]["permissions"] = ["projects/read"]
    mock_response = MagicMock()
    mock_response.json.return_value = nexus_acl
    mock_get = MagicMock(return_value=mock_response)
    monkeypatch.setattr(test_module.requests, "get", mock_get)
    nexus_config.token = nexus_token

    result = test_module.is_user_authorized(nexus_config)

    assert result == 403
    expected_message = (
        "User testuser [Test User] not authorized because of permissions. "
        "Missing: ['events/read', 'gpfs-proj134/read', 'resources/read', 'views/query']"
    )
    assert expected_message in caplog.text
    assert mock_get.call_count == 1


def test_is_user_authorized_false_because_of_endpoint(nexus_config, nexus_token, caplog):
    caplog.set_level(logging.INFO)
    nexus_config.token = nexus_token
    nexus_config.endpoint = "https://fake/endpoint"

    result = test_module.is_user_authorized(nexus_config)

    assert result == 403
    assert (
        "User testuser [Test User] not authorized because of the Nexus endpoint and bucket"
        in caplog.text
    )


def test_is_user_authorized_false_because_of_bucket(nexus_config, nexus_token, caplog):
    caplog.set_level(logging.INFO)
    nexus_config.token = nexus_token
    nexus_config.bucket = "fake/bucket"

    result = test_module.is_user_authorized(nexus_config)

    assert result == 403
    assert (
        "User testuser [Test User] not authorized because of the Nexus endpoint and bucket"
        in caplog.text
    )


def test_is_user_authorized_false_because_of_missing_token(nexus_config, caplog):
    caplog.set_level(logging.INFO)
    nexus_config.token = ""

    result = test_module.is_user_authorized(nexus_config)

    assert result == 401
    assert "Missing authentication token" in caplog.text


def test_is_user_authorized_false_because_of_invalid_token(nexus_config, caplog):
    caplog.set_level(logging.INFO)
    nexus_config.token = "invalid"

    result = test_module.is_user_authorized(nexus_config)

    assert result == 401
    assert "Invalid authentication token" in caplog.text


def test_is_user_authorized_false_because_of_http_error(
    nexus_config, nexus_token, monkeypatch, caplog
):
    caplog.set_level(logging.INFO)
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
        response=MagicMock(status_code=403)
    )
    mock_get = MagicMock(return_value=mock_response)
    monkeypatch.setattr(test_module.requests, "get", mock_get)
    nexus_config.token = nexus_token

    result = test_module.is_user_authorized(nexus_config)

    assert result == 403
    assert (
        "User testuser [Test User] not authorized because of the error from Nexus: 403"
        in caplog.text
    )
    assert mock_get.call_count == 1


def test_is_user_authorized_false_because_of_request_exception(
    nexus_config, nexus_token, monkeypatch, caplog
):
    caplog.set_level(logging.INFO)
    mock_get = MagicMock(side_effect=requests.exceptions.SSLError("SSL Error"))
    monkeypatch.setattr(test_module.requests, "get", mock_get)
    nexus_config.token = nexus_token

    result = test_module.is_user_authorized(nexus_config)

    assert result == 500
    assert (
        "User testuser [Test User] not authorized because of the error from Nexus: SSL Error"
        in caplog.text
    )
    assert mock_get.call_count == 1
