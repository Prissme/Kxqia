"""Initialisation du package dashboard."""
import os
from flask import Flask
from flask_socketio import SocketIO


def create_app(socketio: SocketIO) -> Flask:
    """Crée et configure l'application Flask avec Socket.IO."""
    app = Flask(__name__, template_folder='templates', static_folder='static')
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'change-me')
    return app
