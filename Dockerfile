# Use Python 3.12 slim image to match local environment and scikit-learn version
FROM python:3.12-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Expose the port (FastAPI default is 8000)
# Render manages routing, but we expose this for local testing/port binding
EXPOSE 8000

# Command to run the FastAPI server using Uvicorn
# The PORT environment variable is automatically provided by Render
CMD ["sh", "-c", "uvicorn api:app --host 0.0.0.0 --port ${PORT:-8000}"]
