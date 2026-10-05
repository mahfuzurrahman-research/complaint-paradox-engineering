FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod +x run_public_demo.sh run_signal_demo.sh run_all_demos.sh

CMD ["bash", "run_all_demos.sh"]
