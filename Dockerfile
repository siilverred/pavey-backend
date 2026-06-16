FROM python:3.11-slim

# System deps untuk OpenCV (dibutuhkan PaddleOCR)
RUN apt-get update && apt-get install -y \
    build-essential \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    libgl1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 user
USER user
ENV PATH="/home/user/.local/bin:$PATH"

WORKDIR /home/user/app

COPY --chown=user requirements.txt .
# Install numpy dulu (dibutuhkan paddlepaddle sebelum install)
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir numpy && \
    pip install --no-cache-dir -r requirements.txt

COPY --chown=user . .

# HuggingFace Spaces runs on port 7860
EXPOSE 7860

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]
