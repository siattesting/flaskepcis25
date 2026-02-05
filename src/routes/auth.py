from flask import Blueprint, request, jsonify
from werkzeug.security import check_password_hash, generate_password_hash
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from sqlalchemy import select
from ..models import db, User

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['POST'])
def login():
    """
    Authenticates a human user and returns a JWT.
    Payload: { "username": "admin", "password": "password" }
    """
    data = request.get_json()
    if not data or not data.get('username') or not data.get('password'):
        return jsonify({"message": "Username and password required"}), 400

    # Fetch user
    stmt = select(User).where(User.username == data['username'])
    user = db.session.execute(stmt).scalar_one_or_none()

    # Verify
    if not user or not check_password_hash(user.password_hash, data['password']):
        return jsonify({"message": "Invalid credentials"}), 401

    if not user.is_active:
        return jsonify({"message": "Account disabled"}), 403

    # Generate JWT
    # We embed the role in the token claims so the frontend knows what to show
    additional_claims = {"role": user.role}
    access_token = create_access_token(identity=str(user.id), additional_claims=additional_claims)

    return jsonify({
        "access_token": access_token,
        "user": {
            "id": user.id,
            "username": user.username,
            "role": user.role
        }
    }), 200

@auth_bp.route('/me', methods=['GET'])
@jwt_required()
def me():
    """Returns the currently logged-in user details."""
    current_user_id = get_jwt_identity()
    
    stmt = select(User).where(User.id == current_user_id)
    user = db.session.execute(stmt).scalar_one_or_none()
    
    if not user:
        return jsonify({"message": "User not found"}), 404
        
    return jsonify({
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "plants": "ALL" # Placeholder: In real app, you'd list accessible plants
    }), 200

# --- Utility Route for Setup (Remove in Production) ---
@auth_bp.route('/setup-admin', methods=['POST'])
def setup_admin():
    """Helper to create the first admin user during development."""
    data = request.get_json()
    secret = data.get('admin_secret')
    
    # Simple gatekeeper for this dev route
    import os
    if secret != os.getenv("ADMIN_SETUP_SECRET", "super-secret-setup-key"):
         return jsonify({"message": "Unauthorized"}), 403
         
    if db.session.execute(select(User).where(User.username == "admin")).scalar_one_or_none():
         return jsonify({"message": "Admin already exists"}), 400
         
    new_user = User(
        username="admin",
        password_hash=generate_password_hash(data.get('password', 'admin123')),
        role="admin"
    )
    db.session.add(new_user)
    db.session.commit()
    
    return jsonify({"message": "Admin user created"}), 201