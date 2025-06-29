[Unit]
Description=Madrasa Flask API with Waitress + Auto Git Pull (Root, Port 80)
After=network.target

[Service]
User=root
WorkingDirectory=/home/yourusername/Madrasa_app

# Use virtualenv Python
Environment="PATH=/home/yourusername/Madrasa_app/venv/bin"

# Pull latest code
ExecStartPre=/usr/bin/git reset --hard
ExecStartPre=/usr/bin/git pull

# Start your Python app directly (Waitress runs in it)
ExecStart=/home/yourusername/Madrasa_app/venv/bin/python app.py

Restart=always

[Install]
WantedBy=multi-user.target
