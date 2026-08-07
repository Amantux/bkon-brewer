ARG BUILD_FROM
FROM ${BUILD_FROM}

RUN apk add --no-cache python3 py3-pip bash jq
COPY lightrag_service/requirements.txt /app/requirements.txt
RUN pip install --break-system-packages --no-cache-dir -r /app/requirements.txt
COPY lightrag_service/ /app/
COPY addon/run.sh /run.sh
RUN chmod a+x /run.sh
WORKDIR /app
CMD [ "/run.sh" ]
