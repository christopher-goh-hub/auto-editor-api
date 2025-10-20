FROM python:3.11-alpine AS builder

# Install build dependencies
RUN apk add --no-cache \
    gcc \
    musl-dev \
    python3-dev \
    libffi-dev \
    openssl-dev \
    cargo \
    rust

# Create virtual environment and install Python packages
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Final stage
FROM python:3.11-alpine

# Install runtime dependencies
RUN apk add --no-cache \
    ffmpeg \
    libgomp \
    libstdc++

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Create working directory
WORKDIR /app

# Copy application files
COPY main.py .

# Create directories for uploads and outputs
RUN mkdir -p /tmp/uploads /tmp/outputs

# Expose port
EXPOSE 8000

# Run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
