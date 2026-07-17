ARG CLAVIS_BASE_IMAGE=clavis:local
FROM ${CLAVIS_BASE_IMAGE}

COPY . /opt/clavis-samidare

RUN python -m pip install --no-cache-dir /opt/clavis-samidare
