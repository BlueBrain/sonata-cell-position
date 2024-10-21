Changelog
=========

Version 2024.10.6
-----------------

- Tune nginx cache validity.


Version 2024.10.5
-----------------

- Reorganize routers internally.
- Setup GitHub actions.
- Migrate to uv.
- Add Expires and Cache-Control: max-age response headers.
- First OSS release.


Version 2024.10.4
-----------------

- Cache access to the circuit config file.


Version 2024.10.3
-----------------

- Improve performance of queries when filtering by multiple regions.


Version 2024.10.2
-----------------

- Fix and improve nginx configuration:

  - rewrite ``/api/*`` urls to match the location directives when deployed as a subapp
  - add header ``Cache-Control: private`` to the responses to prevent caching in any intermediate node
  - log upstream_cache_status
  - log millisecond in ISO8601 format

Version 2024.10.1
-----------------

- Support the alternative hierarchy view. [BBPP134-2278]


Version 2024.9.1
-----------------

- Compile all python files.


Version 2024.8.3
-----------------

- Configure nginx to write the cache even when the client disconnects.
- Use python:3.12-slim as base docker image and update deps.

Version 2024.8.2
-----------------

- Breaking change: Remove from the web api the parameter ``input_path``, that was used to specify the path to the circuit_config. Only ``circuit_id`` is now supported.
- Breaking change: Make mandatory the headers: ``nexus-token``, ``nexus-endpoint``, ``nexus-bucket``. Previously, a default value was used when they were missing.
- Return the app name, version, and commit in the /version endpoint, instead of path and commit.
- In case of validation error, do not return input data and log the error.
- Return 401 in case of missing or invalid nexus-* headers, instead of 422.
- Add healthcheck script.

Version 2024.7.9
-----------------

- Ensure that logging is configured in each subprocess.
- Configure structured logs in nginx.


Version 2024.7.8
-----------------

- Use loguru and structured logging.


Version 2024.7.7
-----------------

- Set the required permissions from ACLs on AWS Nexus.
- Set the user id required for k8s deployment in Dockerfile.


Version 2024.7.6
-----------------

- Ensure that the service is exposed only through the reverse proxy.
- Run the service programmatically instead of calling the uvicorn binary.

Version 2024.7.5
-----------------

- Allow to run the image as a non-privileged user.
- Add new nexus endpoint on aws.
- Fix gpfs symlink.
- Ensure that pip doesn't use any cache.
- Add stopasgroup to supervisord to stop the app subprocesses.


Version 2024.7.4
-----------------

- Unify docker images:

    - add supervisord to run nginx
    - upgrade docker image to python 3.12
    - change listening port to 8000
    - run the image as readonly locally, to simulate the k8s deployment
    - add Makefile
    - update README


Version 2024.7.3
-----------------

- Return the correct CORS headers even when returning responses cached by nginx.


Version 2024.7.2
-----------------

- Temporarily pin libsonata==0.1.24.


Version 2024.7.1
-----------------

- Add Nexus integration [NSETM-2283]:

  - The authentication token should be provided in the ``Nexus-Token`` request header in all the ``/circuit`` endpoints.
    If not provided, it's still possible to retrieve resources from Nexus if they aren't private, or from any explicit gpfs path if provided.
  - The Nexus endpoint and bucket can be specified in the request headers ``Nexus-Endpoint`` and ``Nexus-Bucket``.
  - Support Nexus ``circuit_id`` instead of ``input_path`` as a parameter in all the ``/circuit`` endpoints.
  - Retrieve and cache the required resources from Nexus.
  - Retrieve hierarchy.json from Nexus and cache the loaded RegionMap.
  - Add the internal ``/auth`` endpoint, called by the reverse proxy to check the authorization of the user with Nexus.


Version 2024.6.1
-----------------

- Update CORS origins. [BBPP154-256]
- Rewrite circuit caching logic: use a LRUCache, store to disk a partial circuit config with converted node_sets.
- Execute libsonata calls in a subprocess when they are I/O bound. [NSETM-2282]
- Rename endpoint ``/circuit/downsample`` to ``/circuit/sample``.
- Drop support for directly loading ``.h5`` files.
- Upgrade Dockerfile and tests to python 3.11.


Version 2024.1.1
-----------------

- Simplify tox.ini with docker-compose.yml.
- Tune nginx parameters:

  - improve caching performance in accordance with https://www.nginx.com/blog/nginx-caching-guide/#Fine%E2%80%91Tuning-the-Cache-and-Improving-Performance
  - enable gzip compression for known formats:

    - The files are compressed on the fly if the client supports compression, while the cached files aren't compressed when stored.
    - Files with content-type ``application/vnd.apache.parquet`` are not compressed, because they are already compressed by default using the snappy algorythm.
    - Files with content-type ``application/vnd.apache.arrow.file`` are not compressed, although it seems that the only compression currently supported by Arrow is dictionary compression.

Version 2023.12.5
-----------------

- Automate release after tag: when a tag is pushed or added through the GitLab UI, the Docker images are published to the registry and a release is created.

Version 2023.12.4
-----------------

- Tune the reverse proxy parameters:

  - increase inactive time to 24h
  - use min_free instead of max_size
  - exclude /health and /version from the cache
  - change the listening port from 8000 to 8040

Version 2023.12.3
-----------------

- Use nginx-unprivileged as the base image for the reverse proxy.

Version 2023.12.2
-----------------

- Add a reverse proxy in front of the service.

Version 2023.12.1
-----------------

- When querying a circuit, check that each specified region can be resolved to region ids.
- Update ``hierarchy.json``.


Version 2023.11.2
-----------------

- Added new endpoints: /circuit/attribute_names, /circuit/attribute_dtypes, /circuit/attribute_values
- Changed /circuit/downsample from GET to POST.
- Fix json serialization in case of validation error with pydantic v2.
- Move query parameters to arguments.


Version 2023.11.1
-----------------

- Upgrade to Pydantic v2.
- Upgrade requirements.txt.
- Forbid extra attributes in POST endpoints, to prevent potential mistakes in query parameters.
- The endpoint ``/circuit/count`` now accepts only 0 (all) or 1 node populations, for consistency with other endpoints.
- Explicitly require libsonata>=0.1.24 where toJSON() correctly serializes node_sets with node_id.
- Raise the error "nodesets with `node_id` aren't currently supported" only when it's specified a node_set referencing node_id, directly or in a compound expression.


Version 2023.08.1
-----------------

- Improve error handling.


Version 2023.07.1
-----------------

- Add new POST endpoint ``/circuit/query`` to support filtering nodes by any attribute [NSETM-2210]


Version 2023.04.3
-----------------

- Generalize query function in libsonata helper [BBPP134-280]
- Support getting nodes by node_set.
- Allow node_set look ups to happen on cached files.


Version 2023.04.2
-----------------

- Cleanup cache.py and move libsonata functions.


Version 2023.04.1
-----------------

- Remove randomaccessbuffer library.


Version 2023.04.0
-----------------

- Add endpoint ``/circuit/node_sets``.
- Upgrade to python 3.10.
