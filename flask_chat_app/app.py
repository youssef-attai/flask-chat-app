import geventwebsocket
from flask import Flask, render_template
from flask_socketio import SocketIO, emit
from gevent.pywsgi import WSGIServer
from geventwebsocket.handler import WebSocketHandler

app = Flask(__name__)
app.config["SECRET_KEY"] = "secret"
socketio = SocketIO(app, async_mode="gevent")


@app.route("/")
def index():
    return render_template("index.html")


@socketio.on("message")
def handle_message(message):
    emit("message", message, broadcast=True)


if __name__ == "__main__":
    server = WSGIServer(("0.0.0.0", 8080), app, handler_class=WebSocketHandler)
    server.serve_forever()
