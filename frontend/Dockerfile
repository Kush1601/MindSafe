FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir flask python-dotenv supabase

COPY . .

EXPOSE 5000

CMD ["python", "app.py"]
