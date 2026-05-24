FROM mcr.microsoft.com/playwright/python:v1.49.1-jammy

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py image_find.py /app/

EXPOSE 7016

CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-7016}"]
