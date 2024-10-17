"""Schemas and validators definitions."""

import hashlib
from collections.abc import Sequence
from functools import lru_cache
from inspect import signature
from pathlib import Path
from typing import Annotated, Any

from fastapi import Header, HTTPException, Query
from pydantic import (
    AfterValidator,
    BaseModel as PydanticBaseModel,
    Field,
    ValidationError,
    ValidationInfo,
    model_validator,
)
from starlette.status import HTTP_401_UNAUTHORIZED, HTTP_422_UNPROCESSABLE_ENTITY
from voxcell import RegionMap

from app.config import settings
from app.constants import MODALITIES_REGEX
from app.logger import L
from app.serialize import DEFAULT_SERIALIZER, SERIALIZERS_REGEX
from app.utils import attributes_to_dict, modality_to_attributes


class ValidatedParams:
    """Callable wrapper that can be used as a Dependency in FastAPI to define query parameters.

    If a ValidationError is raised in the callable, then it's converted to HTTPException.

    See also https://github.com/tiangolo/fastapi/discussions/9071
    Based on https://github.com/tiangolo/fastapi/discussions/9071#discussioncomment-5156636

    Usage:
        params: Annotated[Model, Depends(ValidatedParams(Model))]
    or
        params: Annotated[Model, Depends(ValidatedParams(Model.from_params))]
    or
        params: Annotated[Model, Depends(Model.from_params)]
        and decorate the class method `from_params` with @ValidatedParams
    """

    _loc_prefix = "query"

    def __init__(self, callable_obj):
        """Init the wrapper with the given callable_obj."""
        self._callable = callable_obj
        self.__signature__ = signature(callable_obj)

    def __call__(self, *args, **kwargs):
        """Call the wrapped callable."""
        signature(self.__call__).bind(*args, **kwargs)
        try:
            return self._callable(*args, **kwargs)
        except ValidationError as e:
            errors = e.errors(include_url=False, include_context=False, include_input=False)
            for error in errors:
                error["loc"] = (self._loc_prefix, *error["loc"])
            L.info("ValidationError: {}", errors)
            raise self._error(errors) from None

    @staticmethod
    def _error(errors: Sequence[Any]) -> Exception:
        """Return the error to be raised in case of validation error."""
        return HTTPException(HTTP_422_UNPROCESSABLE_ENTITY, detail=errors)


class ValidatedAuthHeaders(ValidatedParams):
    """Subclass of ValidatedParams raising 401_UNAUTHORIZED instead of 422_UNPROCESSABLE_ENTITY.

    This is needed in particular for the /auth endpoint called by nginx, because it would consider
    an error any response code different from 2xx, 401, 403, and it would return 500 to the client.
    """

    _loc_prefix = "headers"

    @staticmethod
    def _error(errors: Sequence[Any]) -> Exception:
        """Return the error to be raised in case of validation error."""
        return HTTPException(HTTP_401_UNAUTHORIZED, detail=errors)


class PathValidator:
    """Validator for paths."""

    def __init__(self, allowed_extensions: set[str] | None = None) -> None:
        """Init the wrapper with the allowed extensions.

        Args:
            allowed_extensions: allowed path extensions. If empty or None, any extension is allowed.
        """
        self._allowed_extensions = {self._format_ext(ext) for ext in allowed_extensions or {}}

    @staticmethod
    def _format_ext(ext: str) -> str:
        """Ensure that the extension starts with a dot."""
        return ext if ext.startswith(".") else f".{ext}"

    @staticmethod
    @lru_cache
    def _exists(path: Path) -> bool:
        """Return True if the path exists, False otherwise.

        Cache the result to prevent multiple accesses to slow filesystems
        (requiring even 0.1-0.2 seconds in some cases).

        It should be used only if it can be assumed that the file cannot be removed.
        """
        return path.exists()

    def __call__(self, input_path: Path) -> Path:
        """Validate the path."""
        if self._allowed_extensions and input_path.suffix not in self._allowed_extensions:
            msg = f"Path invalid because of the extension: {input_path}"
            L.warning(msg)
            raise ValueError(msg)
        if not self._exists(input_path):
            msg = f"Path invalid because non existent: {input_path}"
            L.warning(msg)
            raise ValueError(msg)
        return input_path


# Validated path to circuit config
CircuitConfigPath = Annotated[Path, AfterValidator(PathValidator({".json"})), Query()]


class BaseModel(PydanticBaseModel):
    """Custom BaseModel."""

    model_config = {
        "extra": "forbid",
    }


class FrozenBaseModel(PydanticBaseModel):
    """Frozen BaseModel."""

    model_config = BaseModel.model_config | {
        "frozen": True,
    }


class NexusConfig(BaseModel):
    """Nexus configuration."""

    endpoint: str
    bucket: str
    token: Annotated[str, Field(exclude=True)]

    @property
    def org(self):
        """Return Nexus organization."""
        return self.bucket.partition("/")[0]

    @property
    def project(self):
        """Return Nexus project."""
        return self.bucket.partition("/")[2]

    @model_validator(mode="after")
    def check_endpoint_and_bucket(self, info: ValidationInfo) -> "NexusConfig":
        """Check that the model is initialized with valid endpoint and bucket."""
        if info.context and info.context.get("ignore_nexus_fields_from_cli"):
            return self
        endpoint = settings.NEXUS_READ_PERMISSIONS.get(self.endpoint)
        if endpoint is None:
            raise ValueError(f"Nexus endpoint is invalid: {self.endpoint!r}")
        if endpoint.get(self.bucket) is None:
            raise ValueError(f"Nexus bucket is invalid: {self.bucket!r}")
        return self

    @classmethod
    @ValidatedAuthHeaders
    def from_headers(
        cls,
        nexus_endpoint: Annotated[str, Header()],
        nexus_bucket: Annotated[str, Header()],
        nexus_token: Annotated[str, Header()],
    ) -> "NexusConfig":
        """Return a new instance from the given parameters."""
        return cls(
            endpoint=nexus_endpoint,
            bucket=nexus_bucket,
            token=nexus_token,
        )


class CircuitRef(FrozenBaseModel):
    """Circuit reference, having only one of id and path."""

    id: str | None = None  # Nexus ID. It can be None only when called from the CLI.
    path: CircuitConfigPath | None = None  # Path to the circuit config

    @model_validator(mode="after")
    def check_id_and_path_are_exclusive(self) -> "CircuitRef":
        """Check that the model is initialized with exactly one of circuit id and path."""
        if not self.id and not self.path:
            raise ValueError("circuit id or path must be specified")
        if self.id and self.path:
            raise ValueError("circuit id and path cannot be specified at the same time")
        return self

    @classmethod
    @ValidatedParams
    def from_params(cls, circuit_id: str) -> "CircuitRef":
        """Return a new instance from the given parameters."""
        return CircuitRef(id=circuit_id)


class QueryParams(BaseModel):
    """QueryParams."""

    circuit_id: str
    attributes: list[str]
    population_name: str | None = None
    node_set: str | None = None
    sampling_ratio: Annotated[float, Field(gt=0, le=1)] = 0.01
    seed: Annotated[int, Field(ge=0)] = 0
    how: Annotated[str, Field(pattern=SERIALIZERS_REGEX)] = DEFAULT_SERIALIZER
    use_cache: bool = True
    queries: list[dict[str, Any]] | None = None

    @classmethod
    @ValidatedParams
    def from_simplified_params(
        cls,
        circuit_id: str,
        region: Annotated[list[str] | None, Query()] = None,
        mtype: Annotated[list[str] | None, Query()] = None,
        modality: Annotated[
            list[Annotated[str, Query(pattern=MODALITIES_REGEX)]] | None, Query()
        ] = None,
        population_name: str | None = None,
        node_set: str | None = None,
        sampling_ratio: float = 0.01,
        seed: int = 0,
        how: str = DEFAULT_SERIALIZER,
        use_cache: bool = True,
    ) -> "QueryParams":
        # pylint: disable=too-many-arguments
        """Return a new instance from the given simplified parameters instead of queries."""
        attributes = modality_to_attributes(modality)
        query = attributes_to_dict(region=region, mtype=mtype)
        queries = [query] if query else None
        # the common fields are validated when the model is instantiated
        return cls(
            circuit_id=circuit_id,
            attributes=attributes,
            population_name=population_name,
            node_set=node_set,
            sampling_ratio=sampling_ratio,
            seed=seed,
            how=how,
            use_cache=use_cache,
            queries=queries,
        )


class SampleParams(BaseModel):
    """SampleParams."""

    circuit_id: str
    population_name: str | None = None
    sampling_ratio: float = 0.01
    seed: int = 0


class CircuitCacheKey(FrozenBaseModel):
    """Parameters to be considered as cache key.

    All the attributes need to be hashable.
    """

    circuit_config_path: CircuitConfigPath
    population_name: str
    attributes: tuple[str, ...]
    sampling_ratio: float
    seed: int

    def to_json(self) -> str:
        """Return a json representation of the object."""
        return self.model_dump_json()

    def checksum(self) -> str:
        """Calculate the checksum of the object."""
        content = self.to_json()
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def to_file(self, path: Path | str) -> None:
        """Save the current instance to file."""
        content = self.to_json()
        Path(path).write_text(content, encoding="utf-8")


class CircuitCachePaths(FrozenBaseModel):
    """Collection of paths used for cached sampled circuits."""

    base: Path

    @property
    def circuit_config(self):
        """Return the circuit config file path."""
        return self.base / "circuit_config.json"

    @property
    def nodes(self):
        """Return the nodes file path."""
        return self.base / "nodes.h5"

    @property
    def node_sets(self):
        """Return the node_sets file path."""
        return self.base / "node_sets.json"

    @property
    def metadata(self):
        """Return the metadata file path."""
        return self.base / "metadata.json"

    @property
    def id_mapping(self):
        """Return the id_mapping file path, containing the mapping between old and new node ids."""
        return self.base / "id_mapping.json"

    @property
    def ok(self):
        """Return the OK file path."""
        return self.base / "OK"


class CircuitParams(FrozenBaseModel):
    """Parameters needed to load and work with a sampled circuit."""

    model_config = FrozenBaseModel.model_config | {
        "arbitrary_types_allowed": True,  # needed for RegionMap
    }

    key: CircuitCacheKey
    region_map: RegionMap
    alternative_region_map: dict
