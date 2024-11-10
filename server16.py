import os
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from datetime import datetime

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes
socketio = SocketIO(app, cors_allowed_origins="*")  # Allow all origins for SocketIO

# Set up the database URI
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///user.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Define the User model
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(120), unique=True, nullable=False)  # Updated to use username instead of email
    password = db.Column(db.String(120), nullable=False)

# Define the Message model
class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(120), nullable=False)
    message = db.Column(db.String(500), nullable=False)
    timestamp = db.Column(db.String(50), nullable=False)

# Ensure tables are created
with app.app_context():
    if not os.path.exists('users.db'):
        db.create_all()

# User Sign-Up
@app.route('/sign_up', methods=['POST'])
def sign_up():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    # Check if username already exists
    user = User.query.filter_by(username=username).first()
    if user:
        return jsonify(success=False, message="Username already exists"), 400

    new_user = User(username=username, password=password)
    db.session.add(new_user)
    db.session.commit()

    return jsonify(success=True, message="Sign-up successful")

# User Sign-In
@app.route('/sign_in', methods=['POST'])
def sign_in():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    user = User.query.filter_by(username=username, password=password).first()
    if user:
        return jsonify(success=True, message="Login successful")
    else:
        return jsonify(success=False, message="Invalid username or password"), 401

# Send Message (via HTTP request)
@app.route('/send_message', methods=['POST'])
def send_message():
    data = request.get_json()
    username = data.get('username')
    message = data.get('message')
    timestamp = data.get('timestamp') or datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    new_message = Message(username=username, message=message, timestamp=timestamp)
    db.session.add(new_message)
    db.session.commit()

    # Emit a message to clients (for real-time updates)
    socketio.emit('chat message', {'username': username, 'message': message, 'timestamp': timestamp}, broadcast=True)

    return jsonify(success=True, message="Message sent")

# Retrieve All Messages
@app.route('/get_messages', methods=['GET'])
def get_messages():
    messages = Message.query.all()
    return jsonify(messages=[{'username': msg.username, 'message': msg.message, 'timestamp': msg.timestamp} for msg in messages])

# SocketIO Event to Handle Real-Time Chat Messages
@socketio.on('chat message')
def handle_chat_message(data):
    """Handles chat messages from clients, saves them to the database, and broadcasts them."""
    username = data.get('username')
    message = data.get('message')
    timestamp = data.get('timestamp') or datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    if not username or not message:
        emit('error', {'message': 'Missing data: username or message'})
        return

    # Save message to database
    new_message = Message(username=username, message=message, timestamp=timestamp)
    db.session.add(new_message)
    db.session.commit()

    # Broadcast message to all clients
    emit('chat message', {'username': username, 'message': message, 'timestamp': timestamp}, broadcast=True)

# Run the application with SocketIO and make it accessible on the network
if __name__ == "__main__":
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
