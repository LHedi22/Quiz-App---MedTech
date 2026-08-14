# Cloud Run deploys a container, not a Python interpreter directly - this
# image is what `gcloud run deploy` (see /docs/deploy_cloud_run.sh) ships.
#
# Editable install (`pip install -e .`) rather than a built wheel: the
# project's pyproject.toml only declares Python *packages* via
# tool.setuptools.packages.find (no package_data/MANIFEST.in), so a real
# wheel build would silently drop non-.py runtime files this app actually
# needs at request time - app/config/pdf_template.json (Phase 4's single
# source of truth for PDF/OMR geometry) and
# app/ml/bubble_classifier/model.joblib (the trained bubble classifier). An
# editable install instead points straight at the copied source tree, so
# every file that's actually in the image is actually importable/loadable -
# verified by hitting a real endpoint that touches both files (see
# docs/verify_docker_health.md).
FROM python:3.11-slim

# pyzbar (QR decoding, app/services/qr.py) links against libzbar at runtime,
# not just at pip-install time - omitting this makes decode_qr fail with an
# OSError the moment a real scan comes in, not at build time. opencv-python-
# headless still needs libglib2.0-0 despite being the "headless" build.
# tesseract-ocr is the actual OCR binary pytesseract shells out to
# (app/ml/omr/name_ocr.py) - the pip package alone is just a thin wrapper.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libzbar0 \
    libglib2.0-0 \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml ./
COPY app ./app

RUN pip install --no-cache-dir -e .

# Cloud Run injects $PORT and expects the container to listen on it (default
# 8080 locally/for `docker run`, matching CLOUD_RUN_SERVICE_NAME's own
# default port so `docker run -p 8080:8080` "just works" for local smoke
# testing before any real deploy).
ENV PORT=8080
EXPOSE 8080

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
