#!/bin/bash
set -e

# Install Docker
sudo apt-get update
sudo apt-get install -y docker.io
sudo systemctl enable docker
sudo systemctl start docker
sudo usermod -aG docker $USER

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Create app directory
mkdir -p ~/subsgen
cd ~/subsgen

# Clone repo (public)
git clone https://github.com/prabhakar1234pr/subsgen-backend.git .

# Create .env - user must add GROQ_API_KEY
echo "# Add your Groq API key below" > .env
echo "GROQ_API_KEY=REPLACE_WITH_YOUR_KEY" >> .env

# Build and run
sudo docker build -t subsgen-api .
sudo docker run -d --name subsgen --restart unless-stopped -p 7860:7860 --env-file .env subsgen-api

echo "Setup complete. Add your GROQ_API_KEY to ~/subsgen/.env and run: sudo docker restart subsgen"
