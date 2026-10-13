from app import create_app

app = create_app()

if __name__ == "__main__":
    # Localhost only — no need to allow Python through the public firewall.
    app.run(host="127.0.0.1", port=5000, debug=bool(app.config.get("DEBUG")))
