FROM node:24-bookworm-slim AS transport
WORKDIR /transport
COPY src/worklife/p2p_transport/package*.json ./
RUN npm ci --omit=dev
COPY src/worklife/p2p_transport/*.mjs ./

FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends libstdc++6 libatomic1 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=transport /usr/local/bin/node /usr/local/bin/node
COPY --from=transport /transport /opt/worklife-p2p
WORKDIR /app
COPY pyproject.toml requirements.lock README.md ./
COPY src ./src
RUN pip install --no-cache-dir --require-hashes -r requirements.lock \
    && pip install --no-cache-dir --no-deps . \
    && useradd --create-home --uid 10001 worklife \
    && mkdir /data && chown worklife:worklife /data
USER worklife
ENV WORKLIFE_HOME=/data \
    WORKLIFE_CHAIN_PROFILE=public-testnet-v1 \
    WORKLIFE_P2P_TRANSPORT_DIR=/opt/worklife-p2p \
    PYTHONUNBUFFERED=1
EXPOSE 49737/udp
ENTRYPOINT ["worklife"]
CMD ["p2p", "run", "--port", "49737"]
