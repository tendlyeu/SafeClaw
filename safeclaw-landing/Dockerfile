FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN groupadd -r safeclaw && useradd -m -r -g safeclaw safeclaw

# Make app dir writable by safeclaw (FastHTML writes .sesskey at runtime)
# and tighten data directory for SQLite
RUN mkdir -p data && chown -R safeclaw:safeclaw /app && chmod 770 data

USER safeclaw

EXPOSE 5002

CMD ["python", "main.py"]
