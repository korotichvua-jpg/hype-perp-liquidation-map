FROM python:3.12-slim

WORKDIR /app

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code, snapshot data, and pre-built output
COPY . .

# Expose web service port
EXPOSE 41345

# Run the web server
CMD ["python", "server.py", "--host", "::", "--port", "12312"]
