import gzip
import importlib.resources
import shutil
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import create_autospec

import pytest
from httpx import ASGITransport, AsyncClient
from voxcell import RegionMap

import app.brain_region
import app.cache
import app.libsonata_helper
import app.main
import app.nexus
import app.service
from app.schemas import CircuitRef, NexusConfig

from tests.utils import (
    BRAIN_REGION_GZIP_FILE,
    CIRCUIT_ID,
    CIRCUIT_PATH,
    CIRCUIT_PATH_SINGLE_POPULATION,
    NEXUS_BUCKET,
    NEXUS_ENDPOINT,
    NEXUS_TOKEN,
    clear_cache,
)


@pytest.fixture(autouse=True)
def _circuit_cache_path(tmp_path, monkeypatch) -> None:
    """Set the base path of the circuit cache to an isolated subdir of tmp_path."""
    monkeypatch.setenv("CIRCUIT_CACHE_PATH", str(tmp_path / "circuits"))


@pytest.fixture
def circuit_id() -> str:
    return CIRCUIT_ID


@pytest.fixture
def input_path() -> Path:
    return CIRCUIT_PATH


@pytest.fixture
def input_path_single_population() -> Path:
    return CIRCUIT_PATH_SINGLE_POPULATION


@pytest.fixture
def input_path_copy(input_path, tmp_path) -> Path:
    """Copy the circuit dir to the temporary directory, and return the new path to the config."""
    src = input_path.parent
    dst = tmp_path / src.name
    shutil.copytree(src, dst)
    return dst / input_path.name


@pytest.fixture
def circuit_ref_id() -> CircuitRef:
    """Return CircuitRef initialized from circuit_id."""
    return CircuitRef(id=CIRCUIT_ID)


@pytest.fixture
def circuit_ref_path(input_path) -> CircuitRef:
    """Return CircuitRef initialized from input_path."""
    return CircuitRef(path=input_path)


@pytest.fixture
def nexus_config() -> NexusConfig:
    return NexusConfig(
        endpoint=NEXUS_ENDPOINT,
        bucket=NEXUS_BUCKET,
        token=NEXUS_TOKEN,
    )


@pytest.fixture
def region_map() -> RegionMap:
    """Return an instance of RegionMap loaded from hierarchy.json."""
    ref = importlib.resources.files("app") / "data" / "hierarchy.json"
    with importlib.resources.as_file(ref) as path:
        return RegionMap.load_json(path.absolute())


@pytest.fixture
def hierarchy(tmp_path) -> Path:
    """Return the path to a local copy of hierarchy.json."""
    ref = importlib.resources.files("app") / "data" / "hierarchy.json"
    with importlib.resources.as_file(ref) as path:
        return shutil.copy(path, tmp_path)


@pytest.fixture(scope="session")
def alternative_brain_region_file() -> Path:
    """Return the path to an uncompressed alternative region file."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        output_file = tmp_path / "brainregion.json"
        with (
            open(output_file, "wb") as file_out,
            gzip.open(BRAIN_REGION_GZIP_FILE, "rb") as file_in,
        ):
            file_out.write(file_in.read())
        yield output_file


@pytest.fixture(scope="session")
def alternative_region_map(alternative_brain_region_file) -> dict:
    """Return a region map dict loaded from the alternative brain region file."""
    return app.brain_region.load_alternative_region_map(alternative_brain_region_file)


@pytest.fixture
async def api_client() -> AsyncIterator[AsyncClient]:
    """Yield an AsyncClient without nexus tokens."""
    async with AsyncClient(
        transport=ASGITransport(app=app.main.app),
        base_url="http://test",
        headers={
            "content-type": "application/json",
        },
    ) as client:
        yield client


@pytest.fixture
async def api_client_with_auth(api_client) -> AsyncIterator[AsyncClient]:
    """Yield an AsyncClient with nexus tokens required for authentication."""
    async with AsyncClient(
        transport=ASGITransport(app=app.main.app),
        base_url="http://test",
        headers={
            "content-type": "application/json",
            "nexus-endpoint": NEXUS_ENDPOINT,
            "nexus-bucket": NEXUS_BUCKET,
            "nexus-token": NEXUS_TOKEN,
        },
    ) as client:
        yield client


@pytest.fixture
def _patch_get_region_map(monkeypatch, region_map) -> None:
    """Patch get_region_map to return the RegionMap loaded from hierarchy.json."""
    m = create_autospec(app.service.get_region_map, return_value=region_map)
    monkeypatch.setattr("app.service.get_region_map", m)
    yield
    assert m.call_count > 0


@pytest.fixture
def _patch_get_alternative_region_map(monkeypatch, alternative_region_map) -> None:
    """Patch get_alternative_region_map to return the dict loaded from regionmap.json."""
    m = create_autospec(app.service.get_alternative_region_map, return_value=alternative_region_map)
    monkeypatch.setattr("app.service.get_alternative_region_map", m)
    yield
    assert m.call_count > 0


@pytest.fixture
def _patch_get_circuit_config_path(monkeypatch, input_path) -> None:
    """Patch get_circuit_config_path to return the path to the circuit used for tests."""
    m = create_autospec(app.service.get_circuit_config_path, return_value=input_path)
    monkeypatch.setattr("app.service.get_circuit_config_path", m)
    yield
    assert m.call_count > 0


@pytest.fixture
def _patch_get_circuit_config_path_copy(monkeypatch, input_path_copy) -> None:
    """Patch get_circuit_config_path to return the path to a copy of the circuit used for tests."""
    m = create_autospec(app.service.get_circuit_config_path, return_value=input_path_copy)
    monkeypatch.setattr("app.service.get_circuit_config_path", m)
    yield
    assert m.call_count > 0


@pytest.fixture(autouse=True)
def _clear_all_caches() -> None:
    with (
        clear_cache(app.cache._get_sampled_circuit_paths),
        clear_cache(app.libsonata_helper.get_node_population_name),
        clear_cache(app.nexus.load_cached_resource),
        clear_cache(app.nexus.load_cached_region_map),
        clear_cache(app.nexus.load_cached_alternative_region_map),
    ):
        yield
