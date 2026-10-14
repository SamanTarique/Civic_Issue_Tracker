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

`render.yaml` is a Python **web service**. In the Dashboard: **New → Blueprint**, pick this repo, and apply it. Render prompts for `STAFF_EMAIL` and `STAFF_PASSWORD`.

| Setting | Value |
|---|---|
| Runtime | Python |
| Build | `pip install -r requirements.txt` |
| Start | `sh scripts/start.sh` |
| Health check | `/` |
| Python | 3.12 (`.python-version`) |

Required env: `SECRET_KEY` (the blueprint generates one), `APP_ENV=production`, `STAFF_EMAIL`, `STAFF_PASSWORD`. Do not set `FIREBASE_AUTH_EMULATOR_HOST`.

The blueprint uses plan `0.5c-512mb` and a 1 GB disk mounted at `/opt/render/project/src/instance` (`DATABASE_URL` and `UPLOAD_FOLDER` point there). Free instances cannot attach a disk, so SQLite and photos would disappear on sleep or redeploy. New Render services default to Python 3.14, which has no wheel for pinned Pillow 10.4.0 and fails the build.

Optional Postgres: set `DATABASE_URL` to the Render Postgres URL (`postgres://` or `postgresql://`). Startup runs the migrations on that database. Leave the blueprint SQLite URL in place for a disk deploy; that path still boots with no Postgres.

`python run.py` is for a laptop. It listens on `127.0.0.1:5000` unless `PORT` is set. Render's scanner cannot see a loopback-only process, and `python wsgi.py` exits immediately because that file does not start a server. `scripts/start.sh` runs gunicorn on `0.0.0.0:$PORT` with one worker and without `--preload` (Render's default `GUNICORN_CMD_ARGS` preloads, then forks a dead SQLite connection).

Tables are created when the process starts. Do not run `flask db upgrade` as a pre-deploy command: that step cannot see the persistent disk.

## Fly.io

`fly launch` can wrap `wsgi:app`. Attach a volume for `instance/` (database + uploads). Set secrets with `fly secrets set SECRET_KEY=... STAFF_EMAIL=...` (do not commit them). Free or low-cost VMs still restart; SQLite on a volume is the honest storage model for this demo.

## Honest limits (read this)

- **SQLite + local disk:** one file, one machine. Backups are your copies of `instance/`. Concurrent writers are limited. This is not a city-scale database.
- **Free-host restarts:** PythonAnywhere, Render, and Fly free tiers recycle processes. Without a persistent disk, `civic.db` and uploads **disappear** when the instance sleeps or is moved.
- **PythonAnywhere free outbound whitelist:** HTTP clients can only reach allowed hosts. **Google login** (Firebase / Google APIs) and **SMTP** (Gmail, Brevo) often fail until you confirm they are allowed or upgrade. Test both **after** deploy; do not assume they work because they worked on your laptop.
- Email send is best-effort. A mail failure never blocks a report.
