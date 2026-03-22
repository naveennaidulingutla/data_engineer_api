FROM python:3.13-slim
WORKDIR /app
RUN apt-get update && apt-get upgrade -y && apt-get clean
COPY requirements.txt .
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["python","app.py"]