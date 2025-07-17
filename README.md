# Madrasa App

A web-based management system for Madrasas, built with Flask and MySQL. The app provides user registration, authentication, payment management, routine scheduling, and admin features.

## Features
- User registration and login
- Admin dashboard
- Payment and transaction management
- Routine and exam scheduling
- Member and people management
- Contact and feedback forms
- Multi-language support

## Tech Stack
- **Backend:** Python, Flask
- **Database:** MySQL
- **Frontend:** Jinja2 templates (HTML/CSS)
- **Other:** PyMySQL, Flask-WTF, Flask-CORS, Waitress

## Project Structure
```
Madrasa_app/
  app.py                # Main Flask app
  config.py             # Configuration
  database/             # DB utilities and backup scripts
  routes/               # Flask Blueprints (user, admin, web)
  static/               # Static files (images, icons)
  templates/            # Jinja2 HTML templates
  uploads/              # Uploaded files
  requirements.txt      # Python dependencies
```

## Setup Instructions
1. **Clone the repository:**
   ```bash
   git clone <repo-url>
   cd Madrasa_app
   ```
2. **Create a virtual environment and activate it:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```
3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
4. **Configure environment variables:**
   - Copy `.env.example` to `.env` and set your MySQL and other secrets.
5. **Set up the database:**
   - Ensure MySQL is running and accessible.
   - Update `config.py` with your DB credentials.
   - Run the app once to auto-create tables:
     ```bash
     python app.py
     ```
6. **Run the app:**
   ```bash
   python app.py
   # or for production
   waitress-serve --host=0.0.0.0 --port=80 app:app
   ```

## Usage
- Access the app at `http://localhost:8000` (or your configured port).
- Admin dashboard: `/admin`
- User registration and login: `/register`, `/login`
- Payment endpoints: `/due_payment`, `/pay_sslcommerz`, etc.

## Contribution
1. Fork the repository
2. Create a new branch (`git checkout -b feature-branch`)
3. Commit your changes
4. Push to your fork and open a Pull Request

## License
This project is licensed under the MIT License. 