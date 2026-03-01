FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create data directory for SQLite — world-writable so the safeclaw service
# container (which runs as non-root) can also write to the shared DB
RUN mkdir -p data && chmod 777 data

EXPOSE 5002

CMD ["python", "main.py"]
