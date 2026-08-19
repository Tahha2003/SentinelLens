FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY sentinellens/ ./sentinellens/
COPY data/ ./data/
COPY eval/ ./eval/
COPY models/ ./models/
COPY db/ ./db/
COPY .env.example .env

# Train model if not present
RUN python eval/train.py

EXPOSE 5000

ENV FLASK_APP=sentinellens.api.app
ENV FLASK_ENV=production

CMD ["flask", "run", "--host=0.0.0.0", "--port=5000"]
