import logging
import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_socketio import SocketIO, emit
from flask_login import (
    LoginManager,
    UserMixin,
    login_user,
    logout_user,
    login_required,
    current_user,
)
from flask_cors import CORS
from pymongo import MongoClient
from pymongo.server_api import ServerApi
from bson.objectid import ObjectId
from gevent.pywsgi import WSGIServer
from geventwebsocket.handler import WebSocketHandler

app = Flask(__name__)


# Configure logging
logging.basicConfig(level=logging.INFO)

# Enable CORS
CORS(app)

app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")
app.config["SESSION_COOKIE_SECURE"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "None"

socketio = SocketIO(app)

# MongoDB configuration
MONGO_URI = os.getenv("MONGO_URI")
logging.info(f"Connecting to MongoDB at {MONGO_URI}")

# Create a new client and connect to the server
client = MongoClient(
    MONGO_URI,
    server_api=ServerApi("1"),
)
db = client["flaskchatapp"]
chat_collection = db["chat"]
user_collection = db["users"]

# Flask-Login configuration
login_manager = LoginManager()
login_manager.init_app(app)


# User model
class User(UserMixin):
    def __init__(self, user_id, username):
        assert isinstance(user_id, str), "user_id must be a string"
        self.user_id = user_id

        assert isinstance(username, str), "user_id must be a string"
        self.username = username

    def get_id(self):
        return self.user_id


@login_manager.user_loader
def load_user(user_id):
    assert isinstance(user_id, str), "user_id must be a string"

    user = user_collection.find_one({"_id": ObjectId(user_id)})
    assert user, "User must exist"

    username = user["username"]
    assert isinstance(username, str), "username must be a string"
    assert len(username) > 0, "username must not be empty"

    return User(user_id, username)


@login_manager.unauthorized_handler
def unauthorized_callback():
    print("Unauthorized")
    return redirect(url_for("login"))


@app.route("/")
@login_required
def index():
    messages = chat_collection.find().sort("timestamp", 1)
    processed_messages = []
    for message in messages:
        user_id = str(message["userId"])
        assert isinstance(user_id, str), "user_id must be a string"

        user = user_collection.find_one({"_id": ObjectId(user_id)})
        assert user, "User must exist"

        processed_message = {
            "text": message["text"],
            "user": {"username": user["username"]},
            "timestamp": message["timestamp"],
        }
        processed_messages.append(processed_message)
    return render_template("index.html", messages=processed_messages)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        user = user_collection.find_one({"username": username})
        if user and user["password"] == password:
            user_id = str(user["_id"])
            user_obj = User(user_id, username)
            login_user(user_obj)
            return redirect(url_for("index"))
        else:
            flash("Invalid username or password. Please try again.", "error")
    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        # Check if the username is already taken
        if user_collection.find_one({"username": username}):
            flash(
                "Username already exists. Please choose a different username.", "error"
            )
        else:
            # Create a new user document
            new_user = {
                "username": username,
                "password": password,
            }
            user_collection.insert_one(new_user)
            flash("Registration successful. Please log in.", "success")
            return redirect(url_for("login"))
    return render_template("register.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


@socketio.on("message")
@login_required
def handle_message(message):
    user_id = current_user.get_id()
    assert isinstance(user_id, str), "user_id must be a string"

    timestamp = datetime.now().timestamp()
    new_message = {
        "text": message["text"],
        "userId": user_id,
        "timestamp": timestamp,
    }
    chat_collection.insert_one(new_message)
    del new_message["_id"]
    emit(
        "message",
        {
            "text": message["text"],
            "user": {"username": current_user.username},
            "timestamp": timestamp,
        },
        broadcast=True,
    )


if __name__ == "__main__":
    server = WSGIServer(("127.0.0.1", 5000), app, handler_class=WebSocketHandler)
    server.serve_forever()
