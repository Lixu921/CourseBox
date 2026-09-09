FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY static ./static
COPY scripts ./scripts

ENV COURSEBOX_HOST=0.0.0.0
ENV COURSEBOX_DB=data/coursebox.db
ENV COURSEBOX_UPLOAD_DIR=uploads

RUN mkdir -p data uploads

EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
