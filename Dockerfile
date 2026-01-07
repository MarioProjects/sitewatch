# Use an official lightweight Python image
FROM python:3.13-slim

# Copy the uv binary from the official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# Set working directory
WORKDIR /app

# Install dependencies using uv
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    uv sync --frozen --no-install-project --no-dev

# Copy your script and other needed files
COPY . .

# Give permissions and setup cron
RUN chmod +x entrypoint.sh

# Install cron
RUN apt-get update && \
    apt-get install -y cron && \
    apt-get clean

# Add crontab file
RUN crontab crontab

# Create a webpage_versions directory
RUN mkdir -p /app/webpage_versions

# Entrypoint script will run cron and keep the container alive
ENTRYPOINT ["./entrypoint.sh"]
