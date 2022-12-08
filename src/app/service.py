"""Service functions."""
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import libsonata
import numpy as np
import pandas as pd
from numpy.random import default_rng

from app.constants import DTYPES, MODALITIES, SAMPLING_RATIO
from app.logger import L
from app.utils import ensure_list, modality_names_to_columns


def _ensure_population_name(name: Optional[str], names: Iterable[str]) -> str:
    """Return the population name if specified, or if there is only one population.

    Raises:
        ValueError if the population name is not specified and there are multiple populations.
    """
    if name:
        return name
    names = list(names)
    if len(names) > 1:
        # population_names is an unordered set, so we don't know which one to choose
        raise ValueError("population_name must be specified when there are multiple populations")
    return names[0]


def _get_node_population(
    path: Path, population_name: Optional[str] = None
) -> Optional[libsonata.NodePopulation]:
    """Load and return a libsonata node population.

    Args:
        path: path to the circuit config file, or nodes file.
        population_name: name of the node population to load.

    Returns:
        The loaded node population.

    """
    if path.suffix == ".json":
        try:
            config = libsonata.CircuitConfig.from_file(path)
            population_name = _ensure_population_name(population_name, config.population_names)
            return config.node_population(population_name)
        except libsonata.SonataError:
            L.warning("Trying to manually parse the circuit configuration")
            config = json.loads(Path(path).read_text(encoding="utf-8"))
            manifest = config.get("manifest", {})
            path = Path(config["networks"]["nodes"][0]["nodes_file"])
            path = Path(*(manifest.get(part, part) for part in path.parts))
    ns = libsonata.NodeStorage(path)
    population_name = _ensure_population_name(population_name, ns.population_names)
    return ns.open_population(population_name)


def _filter_by_key(
    node_population: libsonata.NodePopulation,
    df: pd.DataFrame,
    key: str,
    values: List[Any],
    keep: bool,
) -> pd.DataFrame:
    """Filter a DataFrame based on the given key and values.

    Args:
        node_population: libsonata node population instance.
        df: DataFrame with ids as index.
        key: key to filter.
        values: list of values to filter.
        keep: if True, add the filtering key to the DataFrame.

    Returns:
        The filtered DataFrame.

    """
    ids = df.index.to_numpy()
    selection = libsonata.Selection(ids)
    attribute = node_population.get_attribute(key, selection)
    if values := ensure_list(values) if values else []:
        masks = [attribute == value for value in values]
        mask = masks[0] if len(masks) == 1 else np.all(masks, axis=0)
        ids = ids[mask]
        attribute = attribute[mask]
        df = df.loc[ids]
    if keep:
        df[key] = attribute
    return df


def _export_dataframe(
    node_population: libsonata.NodePopulation,
    query: Dict[str, Any],
    columns: List[str],
    sampling_ratio: float = SAMPLING_RATIO,
    seed: int = 0,
) -> pd.DataFrame:
    """Create and return a DataFrame of attributes filtered as requested.

    Args:
        node_population: libsonata node population instance.
        query: dict of attributes keys and values for filtering, where values can be single or list.
        columns: list of attributes to be exported in the resulting DataFrame.
        sampling_ratio: sampling_ratio of cells to be considered, expressed as float (0.01 = 1%).
        seed: random number generator seed.

    Returns:
        The resulting DataFrame.

    """
    rng = default_rng(seed)
    high = len(node_population)
    ids = rng.choice(high, size=int(high * sampling_ratio), replace=False, shuffle=False)
    ids.sort()
    L.info("Selected random ids: %s", len(ids))
    df = pd.DataFrame(index=ids)
    columns_set = set(columns)
    # Add columns to the filtering query to load all the required attributes.
    # For better performance, keys that filter out more records should go first.
    query = query | {column: None for column in columns if column not in query}
    for key, values in query.items():
        values = ensure_list(values) if values else []
        keep = key in columns_set
        df = _filter_by_key(node_population, df=df, key=key, values=values, keep=keep)
        L.info("Filtered by %s=%s -> %s ids", key, values or "all", len(df))
    # discard the ids in the index
    df.index = pd.RangeIndex(len(df))
    # ensure the desired dtypes
    df = df.astype(DTYPES)
    return df


def export(
    input_path: Path,
    population_name: Optional[str] = None,
    sampling_ratio: float = SAMPLING_RATIO,
    modality_names: Optional[List[str]] = None,
    regions: Optional[List[str]] = None,
    mtypes: Optional[List[str]] = None,
    seed: int = 0,
) -> pd.DataFrame:
    """Return a DataFrame of nodes attributes.

    Args:
        input_path: path to the circuit config file, or nodes file.
        population_name: name of the node population.
        sampling_ratio: sampling_ratio of cells to be considered, expressed as float (0.01 = 1%).
        modality_names: list of modalities, or None to export every modality.
        regions: list of regions for filtering.
        mtypes: list of mtypes for filtering.
        seed: random number generator seed.

    Returns:
        The resulting DataFrame.

    """
    node_population = _get_node_population(input_path, population_name)
    modality_names = modality_names or list(MODALITIES)
    columns = modality_names_to_columns(modality_names)
    query = {"region": regions, "mtype": mtypes}
    return _export_dataframe(
        node_population=node_population,
        sampling_ratio=sampling_ratio,
        query=query,
        columns=columns,
        seed=seed,
    )
