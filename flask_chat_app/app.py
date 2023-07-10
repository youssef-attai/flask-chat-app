# import gevent.monkey
# gevent.monkey.patch_all(thread=False)

import logging
import os
import geventwebsocket
from flask import Flask, render_template, redirect, url_for, request, flash
from flask_socketio import SocketIO, emit
from flask_login import (
    LoginManager,
    UserMixin,
    login_user,
    logout_user,
    login_required,
    current_user,
)

from pymongo import MongoClient
from bson.objectid import ObjectId
from gevent.pywsgi import WSGIServer
from geventwebsocket.handler import WebSocketHandler

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")
socketio = SocketIO(app, async_mode="gevent")


# Flask-Login configuration
login_manager = LoginManager()
login_manager.init_app(app)

# MongoDB configuration
MONGO_URI = os.getenv("MONGO_URI")
logging.info(f"Connecting to MongoDB at {MONGO_URI}")

client = MongoClient(MONGO_URI)
db = client["flaskchatapp"]
chat_collection = db["chat"]
user_collection = db["users"]


# In-memory database
# chat_collection = [
#     {
#         "text": "Hello",
#         "userId": "1",
#     },
# ]
# user_collection = [
#     {
#         "_id": "1",
#         "username": "youssef",
#         "password": "1",
#     },
#     {
#         "_id": "2",
#         "username": "omar",
#         "password": "1",
#     },
#     {
#         "_id": "3",
#         "username": "ashraf",
#         "password": "1",
#     },
# ]


def find_user_by(key, value):
    # for user in user_collection:
    #     if user[key] == value:
    #         return user
    # return None
    return user_collection.find_one(
        {
            key: ObjectId(value) if key == "_id" else value,
        }
    )


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

    user = find_user_by("_id", user_id)
    assert user, "User must exist"

    username = user["username"]
    assert isinstance(username, str), "username must be a string"
    assert len(username) > 0, "username must not be empty"

    return User(user_id, username)


@login_manager.unauthorized_handler
def unauthorized_callback():
    logging.info("User is not logged in")
    return redirect(url_for("login"))


@app.route("/")
@login_required
def index():
    messages = chat_collection.find()
    processed_messages = []
    for message in messages:
        user_id = str(message["userId"])
        assert isinstance(user_id, str), "user_id must be a string"

        user = find_user_by("_id", user_id)
        assert user, "User must exist"

        processed_message = {
            "text": message["text"],
            "user": {"username": user["username"]},
        }
        processed_messages.append(processed_message)
    return render_template("index.html", messages=processed_messages)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        user = find_user_by("username", username)
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
        if find_user_by("username", username):
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
def handle_message(message):
    user_id = current_user.get_id()
    assert isinstance(user_id, str), "user_id must be a string"

    new_message = {
        "text": message["text"],
        "userId": user_id,
    }
    chat_collection.insert_one(new_message)
    del new_message["_id"]

    emit(
        "message",
        {
            "text": message["text"],
            "user": {"username": current_user.username},
        },
        broadcast=True,
    )


if __name__ == "__main__":
    server = WSGIServer(("0.0.0.0", 8080), app, handler_class=WebSocketHandler)
    server.serve_forever()
