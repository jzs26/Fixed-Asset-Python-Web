from flask import Flask
from database import Base, engine
from models import Asset
from routes.assets import assets_bp
from routes.depreciation import depreciation_bp

app = Flask(__name__)

# 1. ADDED: Secret key configuration
# This is required by Flask to securely handle the 'flash' messages 
# used on your web dashboard layout for user feedback alerts.
app.secret_key = 'analyst_portfolio_secret_key_here'

# Create tables
Base.metadata.create_all(bind=engine)

app.register_blueprint(assets_bp)
app.register_blueprint(depreciation_bp)


if __name__ == "__main__":
    app.run(debug=True)
