import re

import libsonata
import numpy as np
import pandas as pd
import pytest

import app.libsonata_helper as test_module
from app.constants import DTYPES
from app.errors import CircuitError

from tests.utils import assert_frame_equal, dump_json, load_json


def _get_nodes_df(population_name=None):
    # dict of DataFrames as expected from nodes.h5
    all_dfs = {
        "default": pd.DataFrame(
            data={
                "layer": ["L2", "L6", "L6"],
                "model_template": ["hoc:small_bio-A", "hoc:small_bio-B", "hoc:small_bio-C"],
                "model_type": ["biophysical", "biophysical", "biophysical"],
                "morphology": ["morph-A", "morph-B", "morph-C"],
                "mtype": ["L2_X", "L6_Y", "L6_Y"],
                "region": ["SSp1", "SSp1", "SSp2"],
                "rotation_angle_xaxis": [0.0, -0.245267, 0.0],
                "rotation_angle_yaxis": [0.740369, 0.230114, 1.08943],
                "rotation_angle_zaxis": [-0, 2.67074, -0],
                "x": [101.0, 201.0, 301.0],
                "y": [102.0, 202.0, 302.0],
                "z": [103.0, 203.0, 303.0],
                "@dynamics:holding_current": [0.1, 0.2, 0.3],
            },
        ),
        "default2": pd.DataFrame(
            data={
                "layer": ["L7", "L8", "L8", "L2"],
                "model_template": [
                    "hoc:small_bio",
                    "hoc:small_bio",
                    "hoc:small_bio",
                    "hoc:small_bio",
                ],
                "model_type": ["biophysical", "biophysical", "biophysical", "biophysical"],
                "morphology": ["morph-D", "morph-E", "morph-F", "morph-G"],
                "mtype": ["L7_X", "L8_Y", "L8_Y", "L9_Z"],
                "other1": ["A", "B", "C", "D"],
                "other2": [10, 11, 12, 13],
                "region": ["SSp1", "SSp1", "SSp2/3", "SSp2"],
                "rotation_angle_xaxis": [0.0, 0.0, 0.0, 0.0],
                "rotation_angle_yaxis": [0.0, 0.0, 0.0, 0.0],
                "rotation_angle_zaxis": [0.0, 0.0, 0.0, 0.0],
                "x": [401.0, 501.0, 601.0, 701.0],
                "y": [402.0, 502.0, 602.0, 702.0],
                "z": [403.0, 503.0, 603.0, 703.0],
                "@dynamics:holding_current": [1.1, 1.2, 1.3, 1.4],
            }
        ),
    }
    dtypes = DTYPES | {
        "model_type": "category",
        "model_template": "category",
    }
    all_dfs = {key: df.reset_index(drop=True).astype(dtypes) for key, df in all_dfs.items()}
    return all_dfs[population_name] if population_name else all_dfs


def test_get_node_population_name(input_path_single_population):
    result = test_module.get_node_population_name(input_path_single_population)

    assert result == "default"


def test_get_node_population_name_raises(input_path):
    with pytest.raises(
        CircuitError, match="Exactly one node population must be present in the circuit"
    ):
        test_module.get_node_population_name(input_path)


def test_get_node_population(input_path):
    result = test_module.get_node_population(input_path, population_name="default")

    assert isinstance(result, libsonata.NodePopulation)
    assert result.name == "default"


def test_get_node_population_raises(input_path):
    with pytest.raises(
        CircuitError, match="population_name must be specified when there are multiple populations"
    ):
        test_module.get_node_population(input_path)


def test_get_node_populations(input_path):
    result = test_module.get_node_populations(input_path)
    result = list(result)
    assert len(result) == 2
    for node_population, name in zip(result, ["default", "default2"]):
        assert isinstance(node_population, libsonata.NodePopulation)
        assert node_population.name == name


def test_get_node_sets(input_path):
    result = test_module.get_node_sets(input_path)
    assert isinstance(result, libsonata.NodeSets)
    assert len(result.names) == 12


def test_get_node_sets_raises_on_non_existent_path(input_path, tmp_path):
    content = load_json(input_path)
    new_circuit_path = tmp_path / "config.json"
    dump_json(new_circuit_path, content)

    match = re.escape("Impossible to retrieve the node sets [Path does not exist:")
    with pytest.raises(CircuitError, match=match):
        test_module.get_node_sets(new_circuit_path)


@pytest.mark.parametrize(
    "queries, expected_ids",
    [
        (
            None,
            [0, 1, 2, 3],
        ),
        (
            [],
            [0, 1, 2, 3],
        ),
        (
            [{}],
            [0, 1, 2, 3],
        ),
        (
            [{"mtype": "L8_Y"}],
            [1, 2],
        ),
        (
            [{"mtype": ["L8_Y", "L9_Z"], "morphology": "morph-E"}],
            [1],
        ),
        (
            [{"mtype": "L7_X"}, {"morphology": "morph-F"}],
            [0, 2],
        ),
        (
            [{"region": ["SSp2/3", "SSp2"]}],
            [2, 3],
        ),
    ],
)
def test_query_from_file(input_path, queries, expected_ids):
    result = test_module.query_from_file(
        input_path=input_path,
        population_name="default2",
        queries=queries,
        attributes=["x", "y", "z", "mtype", "@dynamics:holding_current"],
        sampling_ratio=1.0,
        seed=0,
        sort=True,
        with_node_ids=True,
    )
    assert isinstance(result, pd.DataFrame)
    expected_columns = ["x", "y", "z", "mtype", "@dynamics:holding_current"]
    expected = _get_nodes_df("default2").loc[expected_ids, expected_columns]
    assert_frame_equal(result, expected)


def test_query_from_file_with_attributes_none(input_path):
    result = test_module.query_from_file(
        input_path=input_path,
        population_name="default2",
        queries=[{"morphology": "morph-E"}],
        attributes=None,
        sampling_ratio=1.0,
        seed=0,
        sort=True,
        with_node_ids=True,
    )
    assert isinstance(result, pd.DataFrame)
    expected = _get_nodes_df("default2").loc[[1]]
    assert_frame_equal(result, expected)


@pytest.mark.parametrize(
    "node_set, expected_ids",
    [
        (
            None,
            np.array([0, 1, 2]),
        ),
        (
            "Population_default",
            [0, 1, 2],
        ),
        (
            "Population_default2",
            np.array([], dtype=int),
        ),
        (
            "Layer2",
            [0],
        ),
    ],
)
def test_query_from_file_node_set(input_path, node_set, expected_ids):
    result = test_module.query_from_file(
        input_path=input_path,
        population_name="default",
        queries=None,
        node_set=node_set,
        attributes=["layer"],
        sampling_ratio=1.0,
        seed=0,
        sort=True,
        with_node_ids=True,
    )

    assert isinstance(result, pd.DataFrame)
    expected = _get_nodes_df("default").loc[expected_ids, ["layer"]]
    assert_frame_equal(result, expected)


def test_query_from_file_with_attributes_empty_list(input_path):
    result = test_module.query_from_file(
        input_path=input_path,
        population_name="default2",
        queries=[{"morphology": "morph-E"}],
        attributes=[],
        sampling_ratio=1.0,
        seed=0,
        sort=True,
        with_node_ids=True,
    )
    assert isinstance(result, pd.DataFrame)
    expected = _get_nodes_df("default2").loc[[1], []]
    # check_column_type=False needed to avoid: Attribute "inferred_type" are different
    assert_frame_equal(result, expected, check_column_type=False)


@pytest.mark.parametrize("missing", ["unknown", "@dynamics:unknown"])
def test_query_from_file_with_missing_attribute(input_path, missing):
    pop = "default2"
    with pytest.raises(CircuitError, match=f"Attribute not found in population {pop}: {missing}"):
        test_module.query_from_file(
            input_path=input_path,
            population_name=pop,
            queries=[],
            attributes=["x", "y", "z", "mtype", missing],
            sampling_ratio=1.0,
            seed=0,
            sort=True,
            with_node_ids=True,
        )
