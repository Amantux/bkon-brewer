ARG BUILD_FROM
FROM ${BUILD_FROM}

# The published LightRAG image is the server; on Home Assistant OS we wrap it in
# an add-on so the Supervisor manages it and reads its config. Everything the
# server needs is passed as environment in run.sh from the add-on options.
RUN apk add --no-cache python3 py3-pip bash jq curl \
    && pip install --break-system-packages --no-cache-dir "lightrag-hku[api]"

COPY run.sh /run.sh
RUN chmod a+x /run.sh
CMD [ "/run.sh" ]
