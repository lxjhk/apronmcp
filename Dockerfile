# Base image bundles Chromium + system deps matching Playwright 1.61.
FROM mcr.microsoft.com/playwright/python:v1.61.0-noble

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src

# Pin playwright to the base image's browser version, then install the package.
RUN pip install --no-cache-dir "playwright==1.61.0" \
    && pip install --no-cache-dir .

ENV APRONMCP_TRANSPORT=http
EXPOSE 8000
CMD ["apronmcp"]
