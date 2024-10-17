"""Libsonata helper functions."""

from collections.abc import Iterable, Iterator, Sequence
from functools import lru_cache
from pathlib import Path
from typing import Any

import h5py
import libsonata
import numpy as np
import pandas as pd
from numpy.random import default_rng

from app.constants import DTYPES, DYNAMICS_PREFIX
from app.errors import CircuitError
from app.logger import L
from app.utils import dump_json, ensure_dtypes, ensure_list, load_json, run_subprocess


@lru_cache
def get_node_population_name(path: Path) -> str:
    """Return the single node population name of the circuit."""
    config = libsonata.CircuitConfig.from_file(path)
    if len(config.node_populations) != 1:
        raise CircuitError("Exactly one node population must be present in the circuit")
    return next(iter(config.node_populations))


def get_node_population(
    path: Path,
    population_name: str | None = None,
) -> libsonata.NodePopulation:
    """Load and return a libsonata node population.

    Args:
        path: path to the circuit config file.
        population_name: name of the node population to load.

    Returns:
        The loaded node population.

    """
    population_names = {population_name} if population_name else None
    node_populations = list(get_node_populations(path, population_names))
    if len(node_populations) > 1 and not population_name:
        # population_names is an unordered set, so we don't know which one to choose
        raise CircuitError("population_name must be specified when there are multiple populations")
    if len(node_populations) != 1:
        raise CircuitError("Exactly one node population should have been selected")
    return node_populations[0]


def get_node_populations(
    path: Path,
    population_names: Iterable[str] | None = None,
) -> Iterator[libsonata.NodePopulation]:
    """Load and yield libsonata node populations.

    Args:
        path: path to the circuit config file.
        population_names: names of the node populations to load, or None to load all of them.

    Yields:
        The loaded node populations. The populations are sorted by name to ensure reproducibility
        when working with multiple populations and specific seeds.

    """
    try:
        config = libsonata.CircuitConfig.from_file(path)
        for population_name in sorted(population_names or config.node_populations):
            yield config.node_population(population_name)
    except libsonata.SonataError as ex:
        raise CircuitError(f"Impossible to retrieve the node population(s) [{ex}]") from ex


def _filter_add_key(
    node_population: libsonata.NodePopulation,
    df: pd.DataFrame,
    key: str,
    values: list[Any],
    keep: bool,
) -> pd.DataFrame:
    """Filter a DataFrame based on the given key and values, and add the key as column.

    Args:
        node_population: libsonata node population instance.
        df: DataFrame with sorted unique ids as index (it may be modified by the function).
        key: key to filter.
        values: list of values to filter, or empty to not apply any filter.
        keep: if True, add the filtering key as a column to the DataFrame.

    Returns:
        The filtered DataFrame (it may be a copy, or the original modified DataFrame).
    """

    def _get_attribute(ids: np.ndarray) -> np.ndarray | pd.Categorical:
        if len(ids) == 0:
            selection = libsonata.Selection([])
        elif len(ids) == node_population.size:
            # since the ids are complete and already sorted, this is faster
            selection = libsonata.Selection([(0, len(ids))])
        else:
            selection = libsonata.Selection(ids)
        if key in node_population.enumeration_names:
            return pd.Categorical.from_codes(
                node_population.get_enumeration(key, selection),
                categories=node_population.enumeration_values(key),
            )
        if key in node_population.attribute_names:
            return node_population.get_attribute(key, selection)
        if key.startswith(DYNAMICS_PREFIX):
            stripped_key = key.removeprefix(DYNAMICS_PREFIX)
            if stripped_key in node_population.dynamics_attribute_names:
                return node_population.get_dynamics_attribute(stripped_key, selection)
        raise CircuitError(f"Attribute not found in population {node_population.name}: {key}")

    ids = df.index.to_numpy()
    attribute = _get_attribute(ids)
    if values:
        if len(values) == 1:
            mask = attribute == values[0]
        elif isinstance(attribute, pd.Categorical):
            mask = attribute.isin(np.asarray(values))
        else:
            mask = np.isin(attribute, np.asarray(values))
        ids = ids[mask]
        attribute = attribute[mask]
        df = df.loc[ids]
    if keep:
        df[key] = attribute
    return df


def _get_sorted_choice(a: np.ndarray | int, sampling_ratio: float, seed: int) -> np.ndarray:
    """Return an array of sorted integer ids, sampled at sampling_ratio."""
    if sampling_ratio >= 1:
        return np.arange(a) if isinstance(a, int) else np.sort(a)
    rng = default_rng(seed)
    full_size = a if isinstance(a, int) else len(a)
    # if 'a' is an integer, do not build an array from it, because
    # it's more performant to pass an int instead of an array to rng.choice
    ids = rng.choice(a, size=int(full_size * sampling_ratio), replace=False, shuffle=False)
    return np.sort(ids)


def _init_ids(
    input_path: Path,
    node_population: libsonata.NodePopulation,
    seed: int,
    node_set: str | None,
    sampling_ratio: float,
) -> np.ndarray:
    """Return the sorted initial list of node ids to consider.

    Args:
        input_path: path to the circuit config file.
        node_population: libsonata node population instance.
        seed: random number generator seed.
        node_set: name of a node_set to load.
        sampling_ratio: sampling_ratio of cells to be considered, expressed as float (0.01 = 1%).
    """
    if node_set:
        ns = get_node_sets(input_path)
        try:
            # If any node sets contain node ids, they must have been previously converted
            # to the ids of the sampled circuit.
            a = ns.materialize(node_set, node_population).flatten().astype("int64")
        except libsonata.SonataError as ex:
            raise CircuitError(str(ex)) from ex
        full_size = len(a)
    else:
        a = full_size = len(node_population)
    ids = _get_sorted_choice(a, sampling_ratio=sampling_ratio, seed=seed)
    L.info(
        "Selected ids from {} in node_population {} with node_set {}: {}/{}",
        input_path,
        node_population.name,
        node_set,
        len(ids),
        full_size,
    )
    return ids


def _build_df_list(
    ids: np.ndarray,
    queries: Sequence[dict[str, Any]] | None,
    node_population: libsonata.NodePopulation,
    attributes: Sequence[str],
) -> list[pd.DataFrame]:
    """Build and return a list of DataFrames, one for each query."""
    df_list: list[pd.DataFrame] = []
    attributes = list(attributes)
    attributes_set = set(attributes)
    # if queries is empty, an empty query dict is needed to select the attributes
    for num, query_dict in enumerate(queries or [{}], 1):
        L.info("Starting {}", f"filter {num}/{len(queries)}" if queries else "export")
        if df_list:
            # remove from ids the ids already selected
            ids = np.setdiff1d(ids, df_list[-1].index.to_numpy(), assume_unique=True)
        # Add attributes to the filtering query to load all the required attributes.
        # For better performance, keys that filter out more records should go first.
        query_dict = query_dict | {col: [] for col in attributes if col not in query_dict}  # noqa: PLW2901
        df = pd.DataFrame(index=ids)
        for key, values in query_dict.items():
            values = ensure_list(values) if values else []  # noqa: PLW2901
            keep = key in attributes_set
            df = _filter_add_key(node_population, df=df, key=key, values=values, keep=keep)
            L.info("Filtered by {}={} -> {} ids", key, values or "all", len(df))
        # reorder the columns if needed
        if attributes != df.columns.to_list():
            df = df[attributes]
        df_list.append(df)
    return df_list


@run_subprocess
def query_from_file(  # pylint: disable=too-many-arguments
    input_path: Path,
    population_name: str | None,
    queries: Sequence[dict[str, Any]] | None = None,
    node_set: str | None = None,
    attributes: Sequence[str] | None = None,
    sampling_ratio: float = 1.0,
    seed: int = 0,
    sort: bool = True,
    with_node_ids: bool = True,
    ids: np.ndarray | None = None,
    dtypes: bool = True,
) -> pd.DataFrame:
    """Build and return a DataFrame of nodes from the given population and queries.

    Args:
        input_path: path to the circuit config file.
        population_name: name of the node population.
        queries: list of query dictionaries to select the nodes based on attributes.
        node_set: name of a node_set to load.
        attributes: list of attributes to export, or None to export all the attributes.
        sampling_ratio: sampling_ratio of cells to be considered, expressed as float (0.01 = 1%).
        seed: random number generator seed.
        sort: True to sort the result by node id.
        with_node_ids: True to return the node_ids as index of the resulting DataFrame
        ids: array of node ids to be used directly. It can be used alternatively to sampling_ratio.
        dtypes: if True, ensure the default dtypes (e.g. to convert from float64 to float32)

    Returns:
        pd.DataFrame of nodes with the requested attributes as columns.
    """
    node_population = get_node_population(input_path, population_name)
    if ids is None:
        ids = _init_ids(input_path, node_population, seed, node_set, sampling_ratio)

    if attributes is not None:
        selected_attributes = attributes
    else:
        selected_attributes = [
            *sorted(node_population.attribute_names),
            *sorted(f"{DYNAMICS_PREFIX}{n}" for n in node_population.dynamics_attribute_names),
        ]
    df_list = _build_df_list(
        ids, queries=queries, node_population=node_population, attributes=selected_attributes
    )
    if len(df_list) == 1:
        # ids are already sorted
        result = df_list[0]
    else:
        result = pd.concat(df_list)
        result = result.sort_index() if sort else result
    if not with_node_ids:
        # discard the ids in the index
        result.index = pd.RangeIndex(len(result))
    if dtypes:
        result = ensure_dtypes(result, dtypes=DTYPES)
    return result


def get_node_sets(input_path: Path) -> libsonata.NodeSets:
    """Return the libsonata.NodeSets.

    Args:
        input_path: path to the circuit config file.

    Returns:
        A dict containing the node_sets from the circuit_config.

    Raises:
        CircuitError. Examples of wrapped exceptions:

        - RuntimeError: Path `` is not a file (if the key "node_sets_file" is missing)
        - RuntimeError: Path `/path/to/node_sets.json` is not a file (if the file doesn't exist)
        - RuntimeError: [json.exception.parse_error.101] parse error... (if the file is invalid)
        - RuntimeError: (without description if the config file is invalid, in some cases)
        - libsonata.SonataError: Error parsing config (if the config file is json, but invalid)
        - libsonata.SonataError: Path does not exist (if the node_sets file doesn't exist)
    """
    try:
        cc = libsonata.CircuitConfig.from_file(input_path)
        ns = libsonata.NodeSets.from_file(cc.node_sets_path)
    except (RuntimeError, libsonata.SonataError) as ex:
        raise CircuitError(f"Impossible to retrieve the node sets [{ex}]") from ex
    return ns


def _dump_id_mapping(output_file: Path, id_mapping: dict[str, np.ndarray]) -> None:
    """Write the id mappings between the old and new populations."""
    result = {population: array.tolist() for population, array in id_mapping.items()}
    dump_json(output_file, result)
    L.info("Dumped id mapping")


def _load_id_mapping(input_file: Path) -> dict[str, np.ndarray]:
    """Read the id mappings between the old and new populations."""
    L.info("Loading id mapping")
    id_mapping = load_json(input_file)
    return {population: np.asarray(lst) for population, lst in id_mapping.items()}


def _convert_ids(ids: np.ndarray, ids_map: pd.Series) -> np.ndarray:
    """Return the given ids converted using ids_map.

    Args:
        ids: array or list of ids to be converted.
        ids_map: pd.Series having the old ids as index, and the new ids as values.

    Returns:
        numpy array of converted ids.
    """
    ids = np.intersect1d(ids, ids_map.index, assume_unique=False)
    return ids_map.loc[ids].to_numpy()


@run_subprocess
def sample_nodes(
    input_path: Path,
    output_path: Path,
    population_name: str,
    sampling_ratio: float = 0.01,
    seed: int = 0,
    attributes: Iterable[str] | None = None,
    id_mapping_path: Path | None = None,
) -> None:
    """Sample a nodes file."""

    # pylint: disable=too-many-locals
    def _filter_attributes(names: set[str]):
        if attributes:
            names = names.intersection(attributes)
        yield from sorted(names)

    rng = default_rng(seed)
    str_dt = h5py.special_dtype(vlen=str)
    L.info(
        "Writing file {} for input_path={}, "
        "population_name={}, sampling_ratio={}, seed={}, attributes={}",
        output_path,
        input_path,
        population_name,
        sampling_ratio,
        seed,
        attributes,
    )
    # map node_population_name -> numpy array of sampled node ids
    sampled_node_ids: dict[str, np.ndarray] = {}
    with h5py.File(output_path, "w") as h5f:
        node_population = get_node_population(input_path, population_name)
        high = len(node_population)
        ids = rng.choice(high, size=int(high * sampling_ratio), replace=False, shuffle=False)
        ids.sort()
        L.info("Sampled ids: {}/{}", len(ids), high)
        selection = libsonata.Selection(ids)
        sampled_node_ids[population_name] = ids
        population_group = h5f.create_group(f"/nodes/{node_population.name}")
        population_group.create_dataset("node_type_id", data=np.full(len(ids), -1))
        group = population_group.create_group("0")
        for name in _filter_attributes(node_population.enumeration_names):
            L.info("Writing enumeration: {}", name)
            data = node_population.enumeration_values(name)
            group.create_dataset(f"@library/{name}", data=data, dtype=str_dt)
            data = node_population.get_enumeration(name, selection)
            group.create_dataset(name, data=data, dtype=data.dtype)
        for name in _filter_attributes(node_population.dynamics_attribute_names):
            L.info("Writing dynamics_attribute: {}", name)
            data = node_population.get_dynamics_attribute(name, selection)
            group.create_dataset(f"dynamics_params/{name}", data=data, dtype=data.dtype)
        for name in _filter_attributes(
            node_population.attribute_names - node_population.enumeration_names
        ):
            L.info("Writing attribute: {}", name)
            data = node_population.get_attribute(name, selection)
            dtype = str_dt if data.dtype == object else data.dtype
            group.create_dataset(name, data=data, dtype=dtype)
    if id_mapping_path:
        _dump_id_mapping(id_mapping_path, sampled_node_ids)


def convert_nodesets(
    input_path: Path,
    output_path: Path,
    id_mapping_path: Path,
) -> None:
    """Convert a node sets file using the given mapping.

    Args:
        input_path: path to the original circuit config file.
        output_path: path to the node sets file to be written.
        id_mapping_path: path to the file containing the id mapping.
    """
    config = libsonata.CircuitConfig.from_file(str(input_path))
    if not config.node_sets_path:
        L.info("The original node sets file doesn't exist, skipping conversion")
    mapping_per_population = {
        population_name: pd.Series(data=np.arange(len(array)), index=array)
        for population_name, array in _load_id_mapping(id_mapping_path).items()
    }
    node_sets = load_json(config.node_sets_path)
    for node_set_name, node_set in node_sets.items():
        if isinstance(node_set, dict) and "node_id" in node_set:
            if "population" in node_set and node_set["population"] in mapping_per_population:
                L.info("Converting node set {!r}", node_set_name)
                mapping = mapping_per_population[node_set["population"]]
                node_set["node_id"] = _convert_ids(node_set["node_id"], mapping).tolist()
            else:
                # invalidate node_ids so that the node_set cannot return wrong ids
                node_set["node_id"] = []
    dump_json(output_path, node_sets)


def write_circuit_config(
    circuit_config_path: Path,
    node_sets_path: Path | None,
    nodes_path: Path,
    node_populations: list[str],
) -> None:
    """Write a partial circuit config file."""
    circuit_config = {
        "version": "2",
        "metadata": {"status": "partial"},
        "node_sets_file": str(node_sets_path or ""),
        "networks": {
            "nodes": [
                {
                    "nodes_file": str(nodes_path),
                    "populations": {population_name: {} for population_name in node_populations},
                }
            ],
            "edges": [],
        },
    }
    dump_json(circuit_config_path, circuit_config)
