from itertools import chain

import libsonata
import pytest
from click.testing import CliRunner

import app.cli as test_module

from tests.utils import _assert_populations_equal, _get_node_population, load_json


def test_export(tmp_path, input_path):
    output_path = tmp_path / "output.json"
    assert not output_path.exists()

    options = [
        ("--input-path", input_path),
        ("--output-path", output_path),
        ("--population-name", "default"),
        ("--sampling-ratio", 0.5),
        ("--modality", "mtype"),
        ("--modality", "position"),
        ("--seed", 102),
        ("--how", "json"),
    ]
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(test_module.cli, ["export", *chain.from_iterable(options)])

    assert result.output == ""
    assert result.exit_code == 0
    assert output_path.is_file()
    assert load_json(output_path) == {
        "mtype": {"0": "L6_Y"},
        "x": {"0": 201.0},
        "y": {"0": 202.0},
        "z": {"0": 203.0},
    }


@pytest.mark.parametrize(
    "params, expected",
    [
        (
            [("--population-name", "default")],
            {"default": [[0], [1]]},
        ),
        (
            [("--population-name", "default2")],
            {"default2": [[0, 1], [1, 3]]},
        ),
    ],
)
def test_sample(tmp_path, input_path, params, expected):
    output_path = tmp_path / "nodes.h5"
    assert not output_path.exists()

    options = [
        ("--input-path", input_path),
        ("--output-path", output_path),
        ("--sampling-ratio", 0.5),
        ("--seed", 103),
        *params,
    ]
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(test_module.cli, ["sample", *chain.from_iterable(options)])

    assert result.output == ""
    assert result.exit_code == 0
    assert output_path.is_file()
    ns = libsonata.NodeStorage(output_path)
    assert ns.population_names == set(expected)
    for population_name, (ids1, ids2) in expected.items():
        node_population = ns.open_population(population_name)
        node_population_orig = _get_node_population(input_path, population_name)
        assert node_population.size == len(ids1) == len(ids2)
        _assert_populations_equal(node_population, node_population_orig, ids1, ids2)
