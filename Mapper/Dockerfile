FROM python:3.13-slim

WORKDIR /app

# Install dependencies first (better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy only what the service needs at runtime
COPY mapper/ ./mapper/
COPY contracts/ ./contracts/
COPY skill/ ./skill/
COPY ucp_specs/ ./ucp_specs/

EXPOSE 8000

CMD ["uvicorn", "mapper.app:app", "--host", "0.0.0.0", "--port", "8000"]
