FROM python:3.13-slim AS builder

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Copy dependency files
COPY pyproject.toml uv.lock* ./
COPY README.md ./

# Install dependencies only
RUN uv sync --frozen --no-install-project --no-dev

# Copy source code
COPY expense_tracker ./expense_tracker

# Build and install the package (non-editable)
RUN uv pip install . --no-deps


FROM python:3.13-slim

WORKDIR /app

# Copy the virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Set PATH to use the virtual environment
ENV PATH="/app/.venv/bin:$PATH"

# Create directory for data persistence
RUN mkdir -p /data/.expense-tracker

# Set environment variable for data directory
ENV HOME=/data

# Run the bot
CMD ["expense-tracker", "bot"]
