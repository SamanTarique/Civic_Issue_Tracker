# Deploy

This app is a **demo**. It is not connected to any real authority. The notes below match a small Flask + SQLite project, not a high-availability civic system.

## PythonAnywhere (free)

1. Create a PythonAnywhere account and open a **Bash** console.
2. Clone the repo into your home directory, for example:
   ```bash
   git clone https://github.com/YOUR_USER/Civic_Issue_Tracker.git
   cd Civic_Issue_Tracker
   ```
3. Create a venv with the same major Python as the web app (3.10 is fine):
   ```bash
   python3.10 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
4. Copy `.env.example` to `.env` in the project root. Set at least:
   - `SECRET_KEY` — long random value, **not** `replace-with-a-long-random-string`
   - `APP_ENV=production`
   - `STAFF_EMAIL` / `STAFF_PASSWORD` (your staff login)
   - `STAFF_DEPARTMENT` (for example `Roads`)
   - Optional Google and SMTP names from `.env.example`
   - `DEMO_MODE=true` only if you want `flask seed-demo` on this host
5. Create folders and migrate:
   ```bash
   mkdir -p instance/uploads
   export FLASK_APP=wsgi.py
   flask db upgrade
   ```
   The first request also creates the staff user from `STAFF_EMAIL` / `STAFF_PASSWORD` if those are set.
6. **WSGI file** (Web → WSGI configuration file). Point it at this repo’s `wsgi.py` and do not enable Flask debug. Example (edit the path and username):
   ```python
   import sys
   path = "/home/YOURUSER/Civic_Issue_Tracker"
   if path not in sys.path:
       sys.path.insert(0, path)
   from wsgi import app as application
   ```
7. **Static files mapping** (Web → Static files):
   - URL `/static/` → directory `/home/YOURUSER/Civic_Issue_Tracker/app/static`
   - Do **not** map `instance/uploads` as static. Photos are only served after login.
8. Reload the web app from the PythonAnywhere Web tab.

### Firebase authorized domain

If Google sign-in is enabled: Firebase console → Authentication → Settings → Authorized domains → add `YOURUSER.pythonanywhere.com`. Keep `localhost` for local work. Do not set `FIREBASE_AUTH_EMULATOR_HOST` in production.

### Post-deploy smoke test

- Open `/` (home, demo banner, map tiles).
- Register a citizen (use **your** email).
- Submit a report with a photo and a map pin.
- Log in as staff; change status (after photo required to mark resolved).
- Confirm a department email arrived if SMTP is configured (check **your** inbox).
- Confirm a photo URL is **not** reachable as a public static file (for example `/static/media/...` should 404). Use the logged-in `/reports/photos/<id>` route only.
- Headers: `curl -I https://YOURUSER.pythonanywhere.com/` and check `Content-Security-Policy`, `X-Frame-Options`, `Referrer-Policy`.

## Render

Create a Web Service from the GitHub repo. Set the start command to a process that serves `wsgi:app` (for example gunicorn if you add it later; this repo does not vendor gunicorn). Set the same `.env` names as environment variables. Use a persistent disk if you need SQLite and uploads to survive restarts. Free instances sleep and lose local files unless you attach a disk.

## Fly.io

`fly launch` can wrap `wsgi:app`. Attach a volume for `instance/` (database + uploads). Set secrets with `fly secrets set SECRET_KEY=... STAFF_EMAIL=...` (do not commit them). Free or low-cost VMs still restart; SQLite on a volume is the honest storage model for this demo.

## Honest limits (read this)

- **SQLite + local disk:** one file, one machine. Backups are your copies of `instance/`. Concurrent writers are limited. This is not a city-scale database.
- **Free-host restarts:** PythonAnywhere, Render, and Fly free tiers recycle processes. Without a persistent disk, `civic.db` and uploads **disappear** when the instance sleeps or is moved.
- **PythonAnywhere free outbound whitelist:** HTTP clients can only reach allowed hosts. **Google login** (Firebase / Google APIs) and **SMTP** (Gmail, Brevo) often fail until you confirm they are allowed or upgrade. Test both **after** deploy; do not assume they work because they worked on your laptop.
- Email send is best-effort. A mail failure never blocks a report.
