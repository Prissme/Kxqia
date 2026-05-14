FROM python:3.11-slim

# --------------------------------------------------
# Environnements Python (stabilité + logs propres)
# --------------------------------------------------
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# --------------------------------------------------
# Workdir
# --------------------------------------------------
WORKDIR /app

# --------------------------------------------------
# Dépendances système minimales (Pillow safe)
# --------------------------------------------------
RUN apt-get update && apt-get install -y \
    gcc \
    libjpeg-dev \
    zlib1g-dev \
    libpng-dev \
    && rm -rf /var/lib/apt/lists/*

# --------------------------------------------------
# Install Python deps (layer cache optimisé)
# --------------------------------------------------
COPY requirements.txt .

RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# --------------------------------------------------
# Copy project
# --------------------------------------------------
COPY . .

# --------------------------------------------------
# Runtime command
# --------------------------------------------------
CMD ["python", "main.py"]