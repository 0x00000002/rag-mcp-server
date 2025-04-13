# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set environment variables to prevent Python from writing pyc files to disc
# and prevent buffering which can interfere with log monitoring
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set the working directory in the container
WORKDIR /app

# Install system dependencies if any (e.g., for specific libraries)
# RUN apt-get update && apt-get install -y --no-install-recommends some-package && rm -rf /var/lib/apt/lists/*

# Install Poetry (or just use pip if you prefer)
# RUN pip install poetry

# Copy only dependency definitions first to leverage Docker cache
COPY pyproject.toml . 
# COPY poetry.lock . # Uncomment if using Poetry

# Install dependencies
# RUN poetry config virtualenvs.create false && poetry install --no-dev --no-interaction --no-ansi # If using Poetry
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir . # Installs dependencies from pyproject.toml

# Copy the rest of the application code
COPY src/ ./src/

# Expose the port the app runs on
EXPOSE 8080

# Define the command to run the application using Uvicorn
# The host 0.0.0.0 makes it accessible from outside the container
CMD ["uvicorn", "src.server:app", "--host", "0.0.0.0", "--port", "8080"] 