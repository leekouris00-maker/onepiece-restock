# The restock bot's container (v2.15). Built by run_docker.bat / docker compose.
# BASE_IMAGE picks the Linux: python:3.12-slim-bookworm (Debian, default) or python:3.12-alpine.
ARG BASE_IMAGE=python:3.12-slim-bookworm
FROM ${BASE_IMAGE}
ARG BASE_IMAGE
ENV BOT_IMAGE=${BASE_IMAGE} \
    BOT_CONTAINER=1 \
    BOT_SECURITY=1 \
    BOT_DATA_DIR=/data \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY docker-requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt && rm /tmp/requirements.txt

# Only the bot's code goes in the image: no config, no secrets, no memory files (see .dockerignore).
COPY *.py /app/
RUN chmod -R a-w /app && mkdir /data && chown 10001:10001 /data

# An unprivileged user with no name, no home and no shell. The compose file also makes the whole
# system read-only, drops every Linux capability and forbids gaining new privileges.
USER 10001:10001
VOLUME ["/data"]
ENTRYPOINT ["python", "-u"]
CMD ["tcg_bot.py", "--loop", "5"]
