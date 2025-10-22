import os
import re
import logging
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from flask_socketio import SocketIO, emit, join_room, leave_room
from datetime import datetime, timedelta
import jwt
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-change-in-production'  # Change this in production!
CORS(app)

# SocketIO configuration
socketio = SocketIO(app, cors_allowed_origins="*", logger=True, engineio_logger=True)

# Database configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///chat_app.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# JWT configuration
JWT_SECRET = 'jwt-secret-change-in-production'  # Change this in production!
JWT_ALGORITHM = 'HS256'

# Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_online = db.Column(db.Boolean, default=False)
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'is_online': self.is_online,
            'last_seen': self.last_seen.isoformat() if self.last_seen else None
        }

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message = db.Column(db.String(1000), nullable=False)
    message_type = db.Column(db.String(20), default='text')  # text, image, file, system
    room = db.Column(db.String(80), default='general')
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    is_edited = db.Column(db.Boolean, default=False)
    edited_at = db.Column(db.DateTime, nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'user_id': self.user_id,
            'message': self.message,
            'message_type': self.message_type,
            'room': self.room,
            'timestamp': self.timestamp.isoformat(),
            'is_edited': self.is_edited,
            'edited_at': self.edited_at.isoformat() if self.edited_at else None
        }

class ChatRoom(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    description = db.Column(db.String(200))
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_private = db.Column(db.Boolean, default=False)

# JWT Authentication Decorator
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({'success': False, 'message': 'Token is missing'}), 401
        
        try:
            if token.startswith('Bearer '):
                token = token[7:]
            data = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            current_user = User.query.get(data['user_id'])
            if not current_user:
                return jsonify({'success': False, 'message': 'User not found'}), 401
        except jwt.ExpiredSignatureError:
            return jsonify({'success': False, 'message': 'Token has expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'success': False, 'message': 'Invalid token'}), 401
        
        return f(current_user, *args, **kwargs)
    return decorated

# Initialize database
with app.app_context():
    db.create_all()
    # Create general room if it doesn't exist
    if not ChatRoom.query.filter_by(name='general').first():
        general_room = ChatRoom(name='general', description='General Chat Room', created_by=1, is_private=False)
        db.session.add(general_room)
        try:
            db.session.commit()
        except Exception as e:
            logger.error(f"Error creating general room: {str(e)}")
            db.session.rollback()

# Utility functions
def validate_password(password):
    if len(password) < 6:
        return False, "Password must be at least 6 characters long"
    return True, ""

def validate_username(username):
    if len(username) < 3:
        return False, "Username must be at least 3 characters long"
    if not re.match(r'^[a-zA-Z0-9_]+$', username):
        return False, "Username can only contain letters, numbers, and underscores"
    return True, ""

# Backward compatible routes (without authentication)
@app.route('/sign_up', methods=['POST', 'OPTIONS'])
def sign_up():
    """Original signup endpoint for backward compatibility"""
    if request.method == 'OPTIONS':
        return jsonify({'success': True})
    
    try:
        data = request.get_json()
        username = data.get('username', '').strip()
        password = data.get('password', '')

        if not username or not password:
            return jsonify({'success': False, 'message': 'Username and password are required'}), 400

        # Check if username already exists
        if User.query.filter_by(username=username).first():
            return jsonify({'success': False, 'message': 'Username already exists'}), 400

        # Create new user
        new_user = User(username=username)
        new_user.set_password(password)
        
        db.session.add(new_user)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Sign-up successful'
        })

    except Exception as e:
        logger.error(f"Signup error: {str(e)}")
        return jsonify({'success': False, 'message': 'Internal server error'}), 500

@app.route('/sign_in', methods=['POST', 'OPTIONS'])
def sign_in():
    """Original signin endpoint for backward compatibility"""
    if request.method == 'OPTIONS':
        return jsonify({'success': True})
    
    try:
        data = request.get_json()
        username = data.get('username', '').strip()
        password = data.get('password', '')

        if not username or not password:
            return jsonify({'success': False, 'message': 'Username and password are required'}), 400

        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            # Update user status
            user.is_online = True
            user.last_seen = datetime.utcnow()
            db.session.commit()

            return jsonify({
                'success': True,
                'message': 'Login successful'
            })
        else:
            return jsonify({'success': False, 'message': 'Invalid username or password'}), 401

    except Exception as e:
        logger.error(f"Signin error: {str(e)}")
        return jsonify({'success': False, 'message': 'Internal server error'}), 500

@app.route('/send_message', methods=['POST', 'OPTIONS'])
def send_message():
    """Original send_message endpoint for backward compatibility"""
    if request.method == 'OPTIONS':
        return jsonify({'success': True})
    
    try:
        data = request.get_json()
        username = data.get('username', '').strip()
        message = data.get('message', '').strip()
        timestamp = data.get('timestamp') or datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        if not username or not message:
            return jsonify({'success': False, 'message': 'Username and message are required'}), 400

        # Find user
        user = User.query.filter_by(username=username).first()
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404

        # Create and save message
        new_message = Message(
            username=username,
            user_id=user.id,
            message=message,
            timestamp=datetime.utcnow()
        )
        
        db.session.add(new_message)
        db.session.commit()

        # Broadcast message to all clients
        socketio.emit('chat message', {
            'username': username,
            'message': message,
            'timestamp': timestamp
        }, broadcast=True)

        return jsonify({'success': True, 'message': 'Message sent'})

    except Exception as e:
        logger.error(f"Send message error: {str(e)}")
        return jsonify({'success': False, 'message': 'Internal server error'}), 500

@app.route('/get_messages', methods=['GET'])
def get_messages():
    """Original get_messages endpoint for backward compatibility"""
    try:
        messages = Message.query.order_by(Message.timestamp.asc()).all()
        messages_data = [{
            'username': msg.username,
            'message': msg.message,
            'timestamp': msg.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        } for msg in messages]
        
        return jsonify({'success': True, 'messages': messages_data})

    except Exception as e:
        logger.error(f"Get messages error: {str(e)}")
        return jsonify({'success': False, 'message': 'Internal server error'}), 500

# Enhanced API routes (with authentication)
@app.route('/api/signup', methods=['POST'])
def api_sign_up():
    """Enhanced signup with JWT"""
    try:
        data = request.get_json()
        username = data.get('username', '').strip()
        password = data.get('password', '')
        email = data.get('email', '').strip()

        if not username or not password:
            return jsonify({'success': False, 'message': 'Username and password are required'}), 400

        is_valid, msg = validate_username(username)
        if not is_valid:
            return jsonify({'success': False, 'message': msg}), 400

        is_valid, msg = validate_password(password)
        if not is_valid:
            return jsonify({'success': False, 'message': msg}), 400

        if User.query.filter_by(username=username).first():
            return jsonify({'success': False, 'message': 'Username already exists'}), 400

        if email and User.query.filter_by(email=email).first():
            return jsonify({'success': False, 'message': 'Email already exists'}), 400

        new_user = User(username=username, email=email)
        new_user.set_password(password)
        
        db.session.add(new_user)
        db.session.commit()

        token = jwt.encode({
            'user_id': new_user.id,
            'username': new_user.username,
            'exp': datetime.utcnow() + timedelta(days=1)
        }, JWT_SECRET, algorithm=JWT_ALGORITHM)

        return jsonify({
            'success': True,
            'message': 'Sign-up successful',
            'token': token,
            'user': new_user.to_dict()
        })

    except Exception as e:
        logger.error(f"API Signup error: {str(e)}")
        return jsonify({'success': False, 'message': 'Internal server error'}), 500

@app.route('/api/signin', methods=['POST'])
def api_sign_in():
    """Enhanced signin with JWT"""
    try:
        data = request.get_json()
        username = data.get('username', '').strip()
        password = data.get('password', '')

        if not username or not password:
            return jsonify({'success': False, 'message': 'Username and password are required'}), 400

        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            # Update user status
            user.is_online = True
            user.last_seen = datetime.utcnow()
            db.session.commit()

            token = jwt.encode({
                'user_id': user.id,
                'username': user.username,
                'exp': datetime.utcnow() + timedelta(days=1)
            }, JWT_SECRET, algorithm=JWT_ALGORITHM)

            return jsonify({
                'success': True,
                'message': 'Login successful',
                'token': token,
                'user': user.to_dict()
            })
        else:
            return jsonify({'success': False, 'message': 'Invalid username or password'}), 401

    except Exception as e:
        logger.error(f"API Signin error: {str(e)}")
        return jsonify({'success': False, 'message': 'Internal server error'}), 500

@app.route('/api/profile', methods=['GET'])
@token_required
def get_profile(current_user):
    return jsonify({'success': True, 'user': current_user.to_dict()})

@app.route('/api/users/online', methods=['GET'])
@token_required
def get_online_users(current_user):
    online_users = User.query.filter_by(is_online=True).all()
    return jsonify({
        'success': True,
        'users': [user.to_dict() for user in online_users]
    })

@app.route('/api/messages', methods=['GET'])
@token_required
def get_messages_enhanced(current_user):
    room = request.args.get('room', 'general')
    limit = min(int(request.args.get('limit', 50)), 100)  # Max 100 messages
    offset = int(request.args.get('offset', 0))

    messages = Message.query.filter_by(room=room)\
        .order_by(Message.timestamp.desc())\
        .offset(offset)\
        .limit(limit)\
        .all()
    
    messages.reverse()  # Return in chronological order
    
    return jsonify({
        'success': True,
        'messages': [msg.to_dict() for msg in messages],
        'room': room
    })

@app.route('/api/messages/<int:message_id>', methods=['PUT'])
@token_required
def edit_message(current_user, message_id):
    try:
        data = request.get_json()
        new_message = data.get('message', '').strip()

        if not new_message:
            return jsonify({'success': False, 'message': 'Message cannot be empty'}), 400

        message = Message.query.get(message_id)
        if not message:
            return jsonify({'success': False, 'message': 'Message not found'}), 404

        if message.user_id != current_user.id:
            return jsonify({'success': False, 'message': 'Cannot edit other users messages'}), 403

        message.message = new_message
        message.is_edited = True
        message.edited_at = datetime.utcnow()
        db.session.commit()

        # Notify clients about the edited message
        socketio.emit('message_edited', {
            'message_id': message.id,
            'new_message': new_message,
            'edited_at': message.edited_at.isoformat(),
            'room': message.room
        }, room=message.room)

        return jsonify({'success': True, 'message': 'Message updated successfully'})

    except Exception as e:
        logger.error(f"Edit message error: {str(e)}")
        return jsonify({'success': False, 'message': 'Internal server error'}), 500

@app.route('/api/rooms', methods=['GET'])
@token_required
def get_rooms(current_user):
    rooms = ChatRoom.query.filter_by(is_private=False).all()
    rooms_data = [{
        'id': room.id,
        'name': room.name,
        'description': room.description,
        'user_count': len(get_room_users(room.name))
    } for room in rooms]
    
    return jsonify({'success': True, 'rooms': rooms_data})

# SocketIO Events
connected_users = {}

def get_room_users(room):
    """Get users in a specific room"""
    return [user_data for user_data in connected_users.values() if room in user_data.get('rooms', [])]

@socketio.on('connect')
def handle_connect():
    logger.info(f"Client connected: {request.sid}")

@socketio.on('disconnect')
def handle_disconnect():
    user_data = connected_users.pop(request.sid, None)
    if user_data:
        user = User.query.get(user_data['user_id'])
        if user:
            user.is_online = False
            user.last_seen = datetime.utcnow()
            db.session.commit()
        
        # Notify about user going offline
        for room in user_data.get('rooms', []):
            emit('user_offline', {
                'user_id': user_data['user_id'],
                'username': user_data['username'],
                'last_seen': user.last_seen.isoformat() if user else datetime.utcnow().isoformat()
            }, room=room)
    
    logger.info(f"Client disconnected: {request.sid}")

@socketio.on('join_room')
def handle_join_room(data):
    try:
        token = data.get('token')
        room = data.get('room', 'general')
        
        if not token:
            emit('error', {'message': 'Authentication required'})
            return

        # Verify token
        user_data = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user = User.query.get(user_data['user_id'])
        
        if not user:
            emit('error', {'message': 'Invalid user'})
            return

        join_room(room)
        
        # Store user connection info
        connected_users[request.sid] = {
            'user_id': user.id,
            'username': user.username,
            'rooms': [room]
        }

        # Update user status
        user.is_online = True
        db.session.commit()

        # Notify room about new user
        emit('user_joined', {
            'user_id': user.id,
            'username': user.username,
            'room': room,
            'online_users': get_room_users(room)
        }, room=room)

        logger.info(f"User {user.username} joined room {room}")

    except Exception as e:
        logger.error(f"Join room error: {str(e)}")
        emit('error', {'message': 'Failed to join room'})

@socketio.on('leave_room')
def handle_leave_room(data):
    room = data.get('room', 'general')
    leave_room(room)
    
    user_data = connected_users.get(request.sid)
    if user_data and room in user_data.get('rooms', []):
        user_data['rooms'].remove(room)
        
        emit('user_left', {
            'user_id': user_data['user_id'],
            'username': user_data['username'],
            'room': room
        }, room=room)

# Backward compatible chat message handling
@socketio.on('chat message')
def handle_legacy_chat_message(data):
    """Handle original chat message format"""
    try:
        username = data.get('username', '').strip()
        message = data.get('message', '').strip()
        timestamp = data.get('timestamp') or datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        if not username or not message:
            emit('error', {'message': 'Username and message are required'})
            return

        user = User.query.filter_by(username=username).first()
        if not user:
            emit('error', {'message': 'User not found'})
            return

        new_message = Message(
            username=username,
            user_id=user.id,
            message=message,
            timestamp=datetime.utcnow()
        )
        
        db.session.add(new_message)
        db.session.commit()

        # Broadcast using original event name
        emit('chat message', {
            'username': username,
            'message': message,
            'timestamp': timestamp
        }, broadcast=True)

        logger.info(f"Legacy message from {username}")

    except Exception as e:
        logger.error(f"Legacy chat message error: {str(e)}")
        emit('error', {'message': 'Failed to send message'})

# Enhanced chat message handling
@socketio.on('send_message')
def handle_enhanced_chat_message(data):
    """Handle enhanced chat message format with authentication"""
    try:
        token = data.get('token')
        message = data.get('message', '').strip()
        room = data.get('room', 'general')
        message_type = data.get('message_type', 'text')

        if not token:
            # Fallback to legacy behavior
            handle_legacy_chat_message(data)
            return

        # Verify token for enhanced functionality
        user_data = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user = User.query.get(user_data['user_id'])
        
        if not user:
            emit('error', {'message': 'Invalid user'})
            return

        if not message:
            emit('error', {'message': 'Message cannot be empty'})
            return

        new_message = Message(
            username=user.username,
            user_id=user.id,
            message=message,
            room=room,
            message_type=message_type,
            timestamp=datetime.utcnow()
        )
        
        db.session.add(new_message)
        db.session.commit()

        # Broadcast to specific room
        emit('chat_message', new_message.to_dict(), room=room)
        logger.info(f"Enhanced message from {user.username} in room {room}")

    except Exception as e:
        logger.error(f"Enhanced chat message error: {str(e)}")
        emit('error', {'message': 'Failed to send message'})

# Typing indicators (compatible with both versions)
@socketio.on('typing')
def handle_typing(data):
    """Handle typing indicators"""
    username = data.get('username') or data.get('user')
    room = data.get('room', 'general')
    
    if username:
        emit('user_typing', {
            'username': username,
            'is_typing': True,
            'room': room
        }, room=room, include_self=False)

@socketio.on('stop_typing')
def handle_stop_typing(data):
    """Handle stop typing indicators"""
    username = data.get('username') or data.get('user')
    room = data.get('room', 'general')
    
    if username:
        emit('user_typing', {
            'username': username,
            'is_typing': False,
            'room': room
        }, room=room, include_self=False)

# Health check endpoint
@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat(),
        'users_online': len([u for u in connected_users.values()])
    })

if __name__ == "__main__":
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)