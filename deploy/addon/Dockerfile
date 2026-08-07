ARG BUILD_FROM
FROM ${BUILD_FROM}

# Debian slim base (see build.yaml). jq reads the add-on options in run.sh; the
# rest is the service and its Python deps. onnxruntime + numpy install as wheels
# here rather than compiling, which is the whole reason for the Debian base.
RUN apt-get update \
    && apt-get install -y --no-install-recommends jq curl \
    && rm -rf /var/lib/apt/lists/*

COPY lightrag_service/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY lightrag_service/ /app/
COPY addon/webroot/ /app/webroot/
COPY addon/run.sh /run.sh
RUN chmod a+x /run.sh
WORKDIR /app
CMD [ "/run.sh" ]
