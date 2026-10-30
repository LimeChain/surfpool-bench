FROM --platform=linux/amd64 python:3.12-bookworm@sha256:a5bab0ff300f91231c2e68bf73a8a8d60762ac39ce1c50eaf6803e4c38a9062b
ARG SURFPOOL_SHA256=5bef2b0b186a74622508f104b6d2e4e2db040932b6d8f3a811172e241f802a63
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates nodejs npm iproute2 procps tcpdump && rm -rf /var/lib/apt/lists/*
COPY images/surfpool-linux-x64.tar.gz /tmp/surfpool.tar.gz
RUN echo "$SURFPOOL_SHA256  /tmp/surfpool.tar.gz" | sha256sum -c - && tar xzf /tmp/surfpool.tar.gz -C /usr/local/bin && rm /tmp/surfpool.tar.gz && surfpool --version
COPY requirements/base.lock /tmp/requirements.lock
RUN pip install --no-cache-dir -r /tmp/requirements.lock && npm install -g @openai/codex@0.155.1
RUN useradd -m -u 1000 agent && useradd -m -u 1001 surfnet && mkdir -p /app /fixtures /logs/agent /logs/artifacts && chown -R agent:agent /app /logs/agent /logs/artifacts
WORKDIR /app
ENV NO_DNA=1
