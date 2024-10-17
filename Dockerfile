# syntax=docker/dockerfile:1.9
ARG UV_VERSION=0.4.22
ARG PYTHON_VERSION=3.12
ARG PYTHON_BASE=${PYTHON_VERSION}-slim

# uv stage
FROM ghcr.io/astral-sh/uv:${UV_VERSION} as uv

# main stage
FROM python:$PYTHON_BASE
SHELL ["bash", "-e", "-x", "-o", "pipefail", "-c"]

# create the app user with the same id used for bbpsbok8sonatacells. See:
# https://bbpgitlab.epfl.ch/cs/kubernetes/flux2-admin/-/blob/3b6fea5/kyverno/gpfs-policies.yml#L499
ARG APP_USER_ID=905632

ARG REQUIRED_PACKAGES="supervisor nginx libnginx-mod-http-js"
ARG OPTIONAL_PACKAGES="vim less curl jq htop strace net-tools iproute2 psmisc procps"

RUN <<EOT
apt-get update -qy
apt-get install -qyy \
    -o APT::Install-Recommends=false \
    -o APT::Install-Suggests=false \
    build-essential \
    ca-certificates \
    ${REQUIRED_PACKAGES} \
    ${OPTIONAL_PACKAGES}
apt-get clean
rm -rf /var/lib/apt/lists/*
EOT

RUN <<EOT
# allow access to circuits on AWS by symlink where the S3 storage is mounted
# (/sbo) to /gpfs. On k8s, this link will be overlayed w/ the real GPFS
ln -sf /sbo/data/project /gpfs
useradd --create-home --shell /bin/sh -u $APP_USER_ID app
EOT

COPY --from=uv /uv /usr/local/bin/uv

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_CACHE_DIR=/code/.cache/uv \
    UV_PYTHON=python${PYTHON_VERSION}

USER app
WORKDIR /code

ENV PATH="/code/.venv/bin:$PATH"
ENV PYTHONPATH="/code:$PYTHONPATH"

RUN echo -e 'alias ll="ls -l"\nalias la="ls -lA"' >> ~/.bash_aliases
COPY --chown=app:app pyproject.toml uv.lock ./

ARG ENVIRONMENT
RUN --mount=type=cache,target=$UV_CACHE_DIR,uid=$APP_USER_ID <<EOT
if [ "${ENVIRONMENT}" = "prod" ]; then
  uv sync --locked --no-install-project --no-dev
elif [ "${ENVIRONMENT}" = "dev" ]; then
  uv sync --locked --no-install-project
else
  echo "Invalid ENVIRONMENT"; exit 1
fi
EOT

COPY ./nginx/ /etc/nginx/
COPY ./supervisord.conf /etc/supervisor/supervisord.conf
COPY --chown=app:app ./src/app/ /code/app/
COPY --chown=app:app ./scripts/healthcheck.sh /code/scripts/healthcheck.sh

RUN python -m compileall app  # compile app files

ARG APP_NAME
ARG APP_VERSION
ARG COMMIT_SHA

ENV ENVIRONMENT=${ENVIRONMENT}
ENV APP_NAME="${APP_NAME}"
ENV APP_VERSION="${APP_VERSION}"
ENV COMMIT_SHA="${COMMIT_SHA}"

RUN <<EOT
python -V
python -m site
python -c 'import app'
EOT

STOPSIGNAL SIGINT
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/supervisord.conf"]
