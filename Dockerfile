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

# 以非 root 用户运行，缩小容器被攻破后的影响面。数据目录要属于该用户，
# 否则 SQLite 与上传写入会因权限失败。
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p data uploads \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
