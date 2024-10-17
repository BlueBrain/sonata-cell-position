import logging

import pytest

import app.cache as test_module

from tests.utils import assert_cache, clear_cache


@pytest.mark.usefixtures("_patch_get_region_map", "_patch_get_alternative_region_map")
def test_get_cached_circuit_params(tmp_path, circuit_ref_path, nexus_config):
    with clear_cache(test_module._get_sampled_circuit_paths) as cached_func:
        # write the cache
        result1 = test_module.get_cached_circuit_params(
            nexus_config=nexus_config,
            circuit_ref=circuit_ref_path,
            population_name="default",
            attributes=["x", "y", "z", "mtype"],
            sampling_ratio=0.5,
            seed=102,
            use_circuit_cache=True,
        )
        assert isinstance(result1, test_module.CircuitParams)
        assert result1.key.sampling_ratio == 1  # sampling_ratio / CACHED_SAMPLING_RATIO
        path1 = result1.key.circuit_config_path
        assert path1.is_file()
        mtime1 = path1.stat().st_mtime_ns
        assert_cache(cached_func, hits=0, misses=1)

        # use the LRU cache
        result2 = test_module.get_cached_circuit_params(
            nexus_config=nexus_config,
            circuit_ref=circuit_ref_path,
            population_name="default",
            attributes=["x", "y", "z", "mtype"],
            sampling_ratio=0.1,
            seed=102,
            use_circuit_cache=True,
        )
        assert isinstance(result2, test_module.CircuitParams)
        assert result2.key.sampling_ratio == 0.2  # sampling_ratio / CACHED_SAMPLING_RATIO
        path2 = result2.key.circuit_config_path
        assert path2.is_file()
        mtime2 = path2.stat().st_mtime_ns
        assert_cache(cached_func, hits=1, misses=1)

        assert path1 == path2, "The cache has not been reused"
        assert mtime1 == mtime2, "The cache has been rewritten"


@pytest.mark.usefixtures("_patch_get_region_map", "_patch_get_alternative_region_map")
def test_get_cached_circuit_params_cache_not_used(tmp_path, circuit_ref_path, nexus_config, caplog):
    caplog.set_level(logging.INFO)
    # cache not used because sampling_ratio is too high
    with clear_cache(test_module._get_sampled_circuit_paths) as cached_func:
        result = test_module.get_cached_circuit_params(
            nexus_config=nexus_config,
            circuit_ref=circuit_ref_path,
            population_name="default",
            attributes=["x", "y", "z", "mtype"],
            sampling_ratio=0.8,
            seed=102,
            use_circuit_cache=True,
        )
        assert isinstance(result, test_module.CircuitParams)
        assert result.key.sampling_ratio == 0.8
        assert_cache(cached_func, hits=0, misses=0, currsize=0)
        assert caplog.record_tuples == [
            ("app.cache", logging.WARNING, "Not caching nor using the sampled circuit")
        ]
