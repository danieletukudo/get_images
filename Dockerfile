# Use the official Python image from the Docker Hub
FROM python:3.10-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV API_KEY=7HDDKgz8kbcwyhrMVuB1uhlWGjRYusdLkMKWjmtBoWDKJ0slp7QlJQQJ99BCACHYHv6XJ3w3AAAAACOGeRlr

# Set the working directory
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt /app/

# Install the dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container
COPY . /app/

# Expose the port the app runs on
EXPOSE 7016

# Set the environment variable for Flask to run in production mode
ENV FLASK_ENV=production

# Start the Flask application
CMD ["flask", "run", "--host", "0.0.0.0", "--port=7016"]