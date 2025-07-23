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

## Deploying with Nginx and Gunicorn

For production, it is recommended to use Nginx as a reverse proxy in front of Gunicorn. Nginx will serve static files and the favicon directly for best performance, and proxy all other requests to Gunicorn.

### 1. Gunicorn
Start your Flask app with Gunicorn (example with 4 workers):

```bash
pip install gunicorn
python run_server.py  # or manually:
gunicorn -w 4 -b 0.0.0.0:8000 app:app
```

### 2. Nginx
Use the provided `nginx.conf` as a template. Update the following line to the absolute path of your project's static directory:

```
    alias   /absolute/path/to/your/project/static/;
```

Place the config in `/etc/nginx/sites-available/yourapp` and symlink it to `/etc/nginx/sites-enabled/`:

```bash
sudo ln -s /etc/nginx/sites-available/yourapp /etc/nginx/sites-enabled/
sudo nginx -t  # test config
sudo systemctl reload nginx
```

- Nginx will serve `/static/` and `/favicon.ico` directly.
- All other requests are proxied to Gunicorn at `http://127.0.0.1:8000`.

See `nginx.conf` in this repo for a full example. 

### 3. Enabling HTTPS with Let's Encrypt

For secure HTTPS, you can use a free SSL certificate from [Let's Encrypt](https://letsencrypt.org/) with Certbot.

#### Steps:
1. **Install Certbot:**
   ```bash
   sudo apt update
   sudo apt install certbot python3-certbot-nginx
   ```
2. **Obtain and install a certificate:**
   Replace `yourdomain.com` with your actual domain name.
   ```bash
   sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com
   ```
   Certbot will automatically update your Nginx config and reload Nginx.

3. **Sample SSL server block:**
   If you want to manually edit your config, add the following to your `nginx.conf`:
   ```nginx
   server {
       listen 443 ssl;
       server_name yourdomain.com www.yourdomain.com;

       ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
       ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;
       include /etc/letsencrypt/options-ssl-nginx.conf;
       ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

       # ... (static, favicon, and proxy config as above) ...
   }

   # Redirect HTTP to HTTPS
   server {
       listen 80;
       server_name yourdomain.com www.yourdomain.com;
       return 301 https://$host$request_uri;
   }
   ```

4. **Auto-renewal:**
   Certbot sets up auto-renewal. You can test renewal with:
   ```bash
   sudo certbot renew --dry-run
   ```

For more details, see the [Certbot documentation](https://certbot.eff.org/). 

## Troubleshooting CSRF and Session Issues (Admin Panel)

If you encounter CSRF errors or cannot log in to the admin panel remotely:

- Make sure all admin forms include the CSRF token (already included in this project).
- Ensure your browser accepts cookies from your domain.
- Always access the admin panel using the same domain and protocol (http/https) as your Flask app is configured for.
- If using HTTPS, set `SESSION_COOKIE_SECURE = True` in `config.py`.
- If using a custom domain, set `SESSION_COOKIE_DOMAIN = ".yourdomain.com"` in `config.py`.
- If using Nginx, ensure these headers are set in your config:
  ```
  proxy_set_header Host $host;
  proxy_set_header X-Real-IP $remote_addr;
  proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
  proxy_set_header X-Forwarded-Proto $scheme;
  ```
- If you see a CSRF error, a user-friendly error page will be shown with the reason.

See `config.py` and `app.py` for more details. 