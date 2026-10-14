from app import create_app
from app.config import listen_address

app = create_app()

if __name__ == "__main__":
    # Loopback unless PORT is set (Render). Production should use scripts/start.sh.
    host, port = listen_address()
    app.run(host=host, port=port, debug=bool(app.config.get("DEBUG")))
