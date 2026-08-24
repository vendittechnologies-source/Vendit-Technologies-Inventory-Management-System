import os

from flask import Flask, jsonify, send_from_directory
from dotenv import load_dotenv

load_dotenv()

from db.seed import seed
from routes.auth_routes import bp as auth_bp, users_bp
from routes.products_routes import bp as products_bp
from routes.lookups_routes import captains_bp, teams_bp, suppliers_bp
from routes.runs_routes import bp as runs_bp
from routes.stock_routes import bp as stock_bp
from routes.purchase_orders_routes import bp as po_bp
from routes.reports_routes import bp as reports_bp

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__, static_folder=os.path.join(BASE_DIR, "static"), static_url_path="/static")

# Create tables (if needed) and the first admin account (if none exists yet)
# as soon as the app module loads. This runs both for local dev (`python
# app.py`) and under a production server like gunicorn (`gunicorn app:app`),
# which never executes the `if __name__ == "__main__"` block below.
seed()

app.register_blueprint(auth_bp)
app.register_blueprint(users_bp)
app.register_blueprint(products_bp)
app.register_blueprint(captains_bp)
app.register_blueprint(teams_bp)
app.register_blueprint(suppliers_bp)
app.register_blueprint(runs_bp)
app.register_blueprint(stock_bp)
app.register_blueprint(po_bp)
app.register_blueprint(reports_bp)


@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Not found."}), 404


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/favicon.ico")
def favicon():
    return "", 204


# ---- Serve the frontend (single-page-ish app with plain HTML pages) ----

TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")


@app.route("/")
def index():
    return send_from_directory(TEMPLATES_DIR, "index.html")


@app.route("/<page>.html")
def page(page):
    safe_pages = {
        "login", "dashboard", "products", "captains", "teams", "suppliers",
        "purchase_orders", "captain_runs", "reports", "users",
    }
    if page not in safe_pages:
        return jsonify({"error": "Not found."}), 404
    return send_from_directory(TEMPLATES_DIR, f"{page}.html")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)
