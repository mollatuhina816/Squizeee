FROM python:3.12-slim
WORKDIR /app
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock
COPY . .
RUN useradd --create-home --uid 10001 quizeee
USER quizeee
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers", "--ws-max-size", "1024", "--ws-max-queue", "4"]
