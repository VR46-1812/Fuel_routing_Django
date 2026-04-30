# Use an official lightweight Python image
FROM python:3.11-slim

# Set environment variables to prevent Python from writing .pyc files
# and to ensure stdout/stderr are unbuffered for Docker logs
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set the working directory
WORKDIR /app

# Install dependencies
COPY requirements.txt /app/
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy the rest of the application code
COPY . /app/

# Expose port 8000 for the Django application
EXPOSE 8000

# Default command to run the Gunicorn WSGI server
# Note: Adjust 'fuel_route_project' if your Django project folder is named differently
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "fuel_route_project.wsgi:application"]
