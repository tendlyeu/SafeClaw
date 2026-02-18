FROM python:3.12-slim

WORKDIR /app

# Install Java for HermiT reasoner (owlready2)
RUN apt-get update && apt-get install -y --no-install-recommends \
    default-jre-headless \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user before installing packages (R3-51)
RUN useradd -m -r safeclaw

COPY pyproject.toml .
COPY safeclaw/ safeclaw/
RUN pip install --no-cache-dir .

USER safeclaw

EXPOSE 8420

CMD ["uvicorn", "safeclaw.main:app", "--host", "0.0.0.0", "--port", "8420"]
