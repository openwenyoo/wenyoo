FROM python:3.11-slim

# Install system dependencies
# lupa requires Lua headers; liblua5.4-dev provides them
RUN apt-get update && apt-get install -y --no-install-recommends \
    liblua5.4-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

# Create runtime directories
RUN mkdir -p saves stories static prompts

# Expose server port
EXPOSE 8000

# Start the server
# config.yaml must be mounted or copied in at runtime (see config.example.yaml)
CMD ["python", "main.py", "--host", "0.0.0.0", "--port", "8000"]
