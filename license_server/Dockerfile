FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server.py .

# SQLite-DB-Verzeichnis muss persistent gemounted werden
VOLUME ["/app/data"]
EXPOSE 8080

ENV LICENSE_DB_PATH=/app/data/licenses.sqlite3
# ADMIN_TOKEN MUSS beim docker run übergeben werden!

CMD ["python", "server.py"]
