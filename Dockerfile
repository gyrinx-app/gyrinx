FROM python:3.12.7-slim

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir --editable .

EXPOSE 8000

CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "gyrinx.asgi:application"]
