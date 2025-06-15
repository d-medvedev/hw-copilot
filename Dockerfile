# Base image for both services
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create and set working directory
WORKDIR /app

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose ports
EXPOSE 8000 8501

# Create a script to run both services
RUN echo '#!/bin/bash\n\
if [ "$SERVICE" = "proxy" ]; then\n\
    cd proxy && uvicorn main:app --host 0.0.0.0 --port 8000\n\
elif [ "$SERVICE" = "streamlit" ]; then\n\
    cd streamlit_app && streamlit run app.py --server.port 8501 --server.address 0.0.0.0\n\
else\n\
    echo "Please specify SERVICE environment variable (proxy or streamlit)"\n\
    exit 1\n\
fi' > /app/entrypoint.sh && chmod +x /app/entrypoint.sh

# Set the entrypoint
ENTRYPOINT ["/app/entrypoint.sh"]