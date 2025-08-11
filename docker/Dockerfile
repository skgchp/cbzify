# CBZify Production Dockerfile - True Distroless & Rootless
# Multi-stage build for minimal attack surface and smallest possible size

# ======================
# Stage 1: Build Stage
# ======================
FROM python:3.11-slim AS builder

# Install system dependencies required for building
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    pkg-config \
    libmupdf-dev \
    libfreetype6-dev \
    libjpeg-dev \
    libopenjp2-7-dev \
    libtiff5-dev \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# Create build directory
WORKDIR /build

# Copy and install Python dependencies
COPY web/requirements-web.txt .
# Update setuptools first to fix CVE-2024-6345 and CVE-2025-47273
RUN pip install --no-cache-dir --user --upgrade "setuptools>=78.1.1"
RUN pip install --no-cache-dir --user -r requirements-web.txt

# ======================
# Stage 2: Python Installation  
# ======================
FROM python:3.11-slim AS python-builder

# Copy Python installation to /usr/local for distroless
RUN cp -r /usr/local/bin /usr/local/lib /usr/local/include /tmp/python-install/ 2>/dev/null || \
    mkdir -p /tmp/python-install && \
    cp -r /usr/local/* /tmp/python-install/

# ======================
# Stage 3: Runtime Libraries
# ======================
FROM python:3.11-slim AS runtime-prep

# Install minimal runtime packages including MuPDF
RUN apt-get update && apt-get install -y --no-install-recommends \
    mupdf \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create directory structure for distroless
RUN mkdir -p /app-structure/uploads /app-structure/downloads && \
    chmod 755 /app-structure /app-structure/uploads /app-structure/downloads

# ======================
# Stage 4: Distroless Final Stage
# ======================
FROM gcr.io/distroless/cc-debian12:nonroot

# Set metadata
LABEL org.opencontainers.image.title="CBZify" \
      org.opencontainers.image.description="Comic converter web interface - PDF/EPUB to CBZ" \
      org.opencontainers.image.vendor="CBZify" \
      org.opencontainers.image.licenses="AGPL-3.0" \
      org.opencontainers.image.source="https://github.com/skgchp/cbzify"

# Copy Python installation from python-builder
COPY --from=python-builder --chown=nonroot:nonroot /usr/local /usr/local

# Copy Python packages from builder stage
COPY --from=builder --chown=nonroot:nonroot /root/.local /home/nonroot/.local

# Copy system libraries from runtime-prep
COPY --from=runtime-prep --chown=nonroot:nonroot /usr/lib /usr/lib
COPY --from=runtime-prep --chown=nonroot:nonroot /lib /lib
COPY --from=runtime-prep --chown=nonroot:nonroot /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/

# Set comprehensive environment variables for distroless Python
ENV PATH="/usr/local/bin:/home/nonroot/.local/bin:$PATH"
ENV PYTHONPATH="/home/nonroot/.local/lib/python3.11/site-packages:/usr/local/lib/python3.11/site-packages"
ENV PYTHONHOME="/usr/local"
ENV LD_LIBRARY_PATH="/usr/local/lib:/usr/lib:/lib"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Copy pre-created app structure
COPY --from=runtime-prep --chown=nonroot:nonroot /app-structure /app
WORKDIR /app

# Copy application files
COPY --chown=nonroot:nonroot src/comic_converter.py .
COPY --chown=nonroot:nonroot web/app.py .
COPY --chown=nonroot:nonroot web/templates/ templates/
COPY --chown=nonroot:nonroot web/static/ static/

# Ensure we're running as nonroot user
USER nonroot

# Expose port (non-privileged)
EXPOSE 8080

# Health check using Python (use full path for reliability)
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD ["/usr/local/bin/python3", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8080/status')"]

# Run the application
CMD ["/usr/local/bin/python3", "app.py"]