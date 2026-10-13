from flask import Blueprint, current_app, jsonify, render_template

from app.services.issues import public_pin_rows, recently_fixed_demo

public_bp = Blueprint("public", __name__)


@public_bp.route("/")
def home():
    return render_template(
        "public/home.html",
        map_default_lat=current_app.config["MAP_DEFAULT_LAT"],
        map_default_lng=current_app.config["MAP_DEFAULT_LNG"],
        recent_fixed=recently_fixed_demo(),
    )


@public_bp.route("/privacy")
def privacy():
    return render_template("public/privacy.html")


@public_bp.route("/api/pins")
def public_pins():
    return jsonify(public_pin_rows())


@public_bp.route("/api/public-pins")
def public_pins_alias():
    return jsonify(public_pin_rows())
