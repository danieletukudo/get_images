FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV SERPER_API_KEY=8894fb6ffd271d200ae416d2f4a2b4acc4f8e3d0

WORKDIR /app

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py image_find.py /app/

EXPOSE 7016

CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-7016}"]
