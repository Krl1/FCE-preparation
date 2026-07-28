# Obraz musi być zgodny z glibc: Claude Code to natywna binarka x86-64 linkowana
# dynamicznie do libc/libm/libpthread. Na Alpine (musl) nie uruchomi się.
FROM python:3.12-slim

# Claude Code NIE jest instalowany w obrazie — binarka i konfiguracja są montowane
# z hosta (patrz compose.yaml). Dzięki temu kontener korzysta z Twojego logowania
# z subskrypcji, nie wymaga klucza API i automatycznie nadąża za aktualizacjami CLI.

# Użytkownik o UID/GID 1000 odpowiada właścicielowi plików na hoście. Bez tego
# kontener nie odczytałby ~/.claude/.credentials.json (prawa 0600) ani nie zapisał
# bazy w podmontowanym katalogu data/.
RUN groupadd --gid 1000 app && useradd --uid 1000 --gid 1000 --create-home --home-dir /home/karol app

WORKDIR /app

# Zależności w osobnej warstwie — zmiana kodu nie unieważnia cache pip.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY static/ ./static/

# Katalog bazy jest montowany jako wolumen, ale musi istnieć i należeć do użytkownika,
# bo SQLite tworzy w nim także pliki -wal i -shm.
RUN mkdir -p /app/data && chown -R 1000:1000 /app

USER 1000:1000

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOME=/home/karol \
    FCE_DB_PATH=/app/data/fce.db \
    FCE_CLAUDE_BIN=/home/karol/.local/bin/claude

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
