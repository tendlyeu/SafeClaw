FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN groupadd -r safeclaw && useradd -r -g safeclaw safeclaw

# Create data directory for SQLite
RUN mkdir -p data && chown safeclaw:safeclaw data && chmod 770 data

USER safeclaw

EXPOSE 5002

CMD ["python", "main.py"]
