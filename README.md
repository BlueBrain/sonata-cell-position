# sonata-cell-position

## Description

This service consists of:

-   a reverse proxy with caching, listening on port 8000, and exposed at 127.0.0.1:8200 when running the Docker image locally
-   the main service, listening on port 8010 and accessed only through the proxy above

This is a simplified request response diagram:

```mermaid
sequenceDiagram
    participant User
    participant Proxy as Proxy:8000
    participant API as API:8010
    participant Nexus
    User->>+Proxy: GET /circuit
    Proxy->>+API: GET /auth
    API->>+Nexus: GET /acls
    Nexus-->>-API: 200 OK
    Note over API: Check permissions
    API-->>-Proxy: 200 OK
    Proxy->>+API: GET /circuit
    API->>+Nexus: GET <resources>
    Nexus-->>-API: 200 OK
    Note over API: Build response
    API-->>-Proxy: 200 OK
    Proxy-->>-User: 200 OK
```

Both the `/auth` and `/circuit` requests can be independently cached on the proxy.


## API Documentation

The API documentation is available at:
- <https://cells.sbo.kcp.bbp.epfl.ch/docs> for the k8s deployment.
- <https://openbluebrain.com/api/circuit/docs> for the AWS deployment.
- <http://127.0.0.1:8200/docs> when running locally in Docker.


## Remote deployment

To make a release, build and publish the Docker image to the Docker Hub  registry, you need to:

-   create a release through the GitHub UI (preferred), or
-   push a tag to the main branch using git.

The format of the tag should be `YYYY.M.N`, where:

-   `YYYY` is the full year (2024, 2025...)
-   `M` is the short month, not zero-padded (1, 2 ... 11, 12)
-   `N` is any incremental number, not zero-padded (it doesn't need to be the day)

The new Docker image is automatically pushed to Docker Hub as part of the CI pipeline.


## Local build and deployment

1. Mount `/gpfs` if not mounted already:

    ```bash
    sshfs $USER@bbpv2.epfl.ch:/gpfs /gpfs -o 'ro,allow_other'
    ```

2. Build and start the Docker image locally:

    ```bash
    make run
    ```

## Try the service from the CLI

1. Assign the nexus token to a variable. You can copy it from the correct instance of Nexus Fusion (on AWS or k8s), or use bbp-workflow-cli (k8s):

    ```bash
    NEXUS_TOKEN=$(bbp-workflow -v get-token)
    ```

2. Set the Nexus variables depending on the environment and replace `CIRCUIT_ID` with the desired circuit id:

   1. Nexus on AWS

      ```bash
      NEXUS_ENDPOINT="https://openbluebrain.com/api/nexus/v1"
      NEXUS_BUCKET="bbp/mmb-point-neuron-framework-model"
      CIRCUIT_ID="https://bbp.epfl.ch/data/bbp/mmb-point-neuron-framework-model/2b29d249-6520-4a98-9586-27ec7803aed2"
      ```

   2. Nexus on k8s prod

      ```bash
      NEXUS_ENDPOINT="https://bbp.epfl.ch/nexus/v1"
      NEXUS_BUCKET="bbp/mmb-point-neuron-framework-model"
      CIRCUIT_ID="https://bbp.epfl.ch/data/bbp/mmb-point-neuron-framework-model/2b29d249-6520-4a98-9586-27ec7803aed2"
      ```

   3. Nexus on k8s staging

      ```bash
      NEXUS_ENDPOINT="https://staging.nise.bbp.epfl.ch/nexus/v1"
      NEXUS_BUCKET="bbp/mmb-point-neuron-framework-model"
      CIRCUIT_ID="https://bbp.epfl.ch/data/bbp/mmb-point-neuron-framework-model/75a2feb8-2a9a-4f31-b50c-49e098a6c1f4"
      ```

3. Set correct API endpoint of the service:

   1. Cell service on AWS:

      ```bash
      API="https://openbluebrain.com/api/circuit"
      ```

   2. Cell service on k8s:

      ```bash
      API="https://cells.sbo.kcp.bbp.epfl.ch"
      ```

   3. Cell service running locally in Docker:

      ```bash
      API="http://127.0.0.1:8200"
      ```

4. Make a call to the `/version` endpoint to know the version of the deployed service:

    ```bash
    curl "$API/version"
    ```
   
5. Make a call to the `/circuit/count` endpoint to get the number of neurons:

    ```bash
    curl -G "$API/circuit/count" \
    --data-urlencode "circuit_id=$CIRCUIT_ID" \
    -H "nexus-token: $NEXUS_TOKEN" \
    -H "nexus-endpoint: $NEXUS_ENDPOINT" \
    -H "nexus-bucket: $NEXUS_BUCKET" \
    -H "content-type: application/json"
    ```
   
6. Make a call to the `/circuit` endpoint to get the positions of cells:

    ```bash
    curl -G "$API/circuit?region=581&how=json" \
    --data-urlencode "circuit_id=$CIRCUIT_ID" \
    -H "nexus-token: $NEXUS_TOKEN" \
    -H "nexus-endpoint: $NEXUS_ENDPOINT" \
    -H "nexus-bucket: $NEXUS_BUCKET" \
    -H "content-type: application/json" \
    -o output.json
    ```


## Acknowledgements

The development of this software was supported by funding to the Blue Brain Project, a research center of the École polytechnique fédérale de Lausanne (EPFL), from the Swiss government’s ETH Board of the Swiss Federal Institutes of Technology.

For license see LICENSE.txt.

Copyright (c) 2022-2024 Blue Brain Project/EPFL
