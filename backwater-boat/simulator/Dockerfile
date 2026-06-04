FROM python:3.11-slim

WORKDIR /app
COPY simulator/requirements.txt /app/simulator/requirements.txt
RUN pip install --no-cache-dir -r /app/simulator/requirements.txt
COPY simulator /app/simulator

CMD ["python", "simulator/cycle_sim.py"]
