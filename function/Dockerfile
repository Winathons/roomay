FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN useradd -m -u 10001 appuser

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir workpeg
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY app /app/app

USER appuser

ENTRYPOINT ["workpeg", "function", "runtime", "--server"]