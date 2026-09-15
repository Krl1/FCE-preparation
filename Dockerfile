# Obraz musi być zgodny z glibc: Claude Code to natywna binarka x86-64 linkowana
# dynamicznie do libc/libm/libpthread. Na Alpine (musl) nie uruchomi się.
FROM python:3.12-slim

# Claude Code NIE jest instalowany w obrazie — binarka i konfiguracja są montowane
# z hosta (patrz compose.yaml). Dzięki temu kontener korzysta z Twojego logowania
# z subskrypcji, nie wymaga klucza API i automatycznie nadąża za aktualizacjami CLI.

# APP_HOME musi być IDENTYCZNY z katalogiem domowym na hoście. Powód: ~/.local/bin/claude
# to symlink ABSOLUTNY (→ /home/<user>/.local/share/claude/versions/X.Y.Z), więc rozwiąże
# się w kontenerze tylko wtedy, gdy montowania leżą dokładnie pod tą samą ścieżką.
# compose.yaml podstawia tu ${HOME} hosta; wartość domyślna służy tylko budowaniu bez compose.
ARG APP_HOME=/home/app

# UID/GID muszą odpowiadać właścicielowi plików na hoście. Bez tego kontener nie odczytałby
# ~/.claude/.credentials.json (prawa 0600) ani nie zapisał bazy w podmontowanym katalogu data/.
# Jeśli Twój użytkownik nie ma 1000, ustaw: export APP_UID=$(id -u) APP_GID=$(id -g).
ARG APP_UID=1000
ARG APP_GID=1000

RUN groupadd --gid ${APP_GID} app \
 && useradd --uid ${APP_UID} --gid ${APP_GID} --create-home --home-dir ${APP_HOME} app

WORKDIR /app

# Zależności w osobnej warstwie — zmiana kodu nie unieważnia cache pip.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY static/ ./static/

# Katalog bazy jest montowany jako wolumen, ale musi istnieć i należeć do użytkownika,
# bo SQLite tworzy w nim także pliki -wal i -shm.
RUN mkdir -p /app/data && chown -R ${APP_UID}:${APP_GID} /app

USER ${APP_UID}:${APP_GID}

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOME=${APP_HOME} \
    FCE_DB_PATH=/app/data/fce.db \
    FCE_CLAUDE_BIN=${APP_HOME}/.local/bin/claude

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
