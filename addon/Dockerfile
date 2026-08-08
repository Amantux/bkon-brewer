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

# Bake the embedding model into the image. LightRAG ships in every build, so it
# should also *work* in every build: without this the ~90 MB ONNX model is
# fetched on first start, which turns a fresh install into a silent download --
# and fails outright on a machine with no route to the internet. Baked in, the
# retrieval half is genuinely self-contained, which is what the service claims.
ENV FASTEMBED_CACHE=/opt/fastembed \
    EMBED_MODEL=BAAI/bge-small-en-v1.5
RUN python -c "from fastembed import TextEmbedding; \
    TextEmbedding('${EMBED_MODEL}', cache_dir='${FASTEMBED_CACHE}')" \
    && find ${FASTEMBED_CACHE} -type f | head -5

COPY lightrag_service/ /app/
COPY webroot/ /app/webroot/
COPY run.sh /run.sh
RUN chmod a+x /run.sh
WORKDIR /app
CMD [ "/run.sh" ]
