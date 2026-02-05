from functools import wraps
from flask import request, jsonify, g, current_app
from werkzeug.security import check_password_hash
from sqlalchemy import select
from ..models import db, Device

def require_device_key(required_role=None):
    """
    Decorator to protect routes using API Keys.
    
    Usage:
        @events_bp.route('/capture', methods=['POST'])
        @require_device_key(required_role='camera')
        def capture_event():
            ...
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # 1. Extract Header
            api_key = request.headers.get('X-Device-Key')
            
            if not api_key:
                return jsonify({
                    "error": "Missing API Key", 
                    "message": "Please provide 'X-Device-Key' header."
                }), 401

            # 2. Find Device in DB
            # Note: In a high-throughput factory (1000+ reads/min), 
            # you would cache this lookup in Redis to save DB hits.
            stmt = select(Device)
            # We don't filter by hash here because we can't query the hash directly.
            # We fetch all devices? No, that's slow. 
            # REAL WORLD: We usually send "Device-ID" AND "Device-Key" to look up the ID 
            # and verify the key. 
            # FOR SIMPLICITY HERE: We will iterate devices or rely on a 'client_id' if provided.
            # IMPROVEMENT: Let's assume the header is "DeviceID:ApiKey". 
            # If not, we have to check all devices which is slow.
            # OPTION B: Store a 'prefix' of the key in DB to narrow down search.
            
            # Let's stick to the most robust method for this phase:
            # We expect the header to be the raw key. We'll search for the device 
            # by a metadata header if possible, but if not, we must rely on a specific lookup.
            # To fix the performance/security gap, let's mandate headers:
            # X-Device-Id: <uuid>
            # X-Device-Key: <secret>
            
            device_id = request.headers.get('X-Device-Id')
            if not device_id:
                 return jsonify({"error": "Missing Device ID", "message": "X-Device-Id header required"}), 400

            device = db.session.execute(select(Device).where(Device.id == device_id)).scalar_one_or_none()

            if not device:
                 return jsonify({"error": "Invalid Device", "message": "Device not registered"}), 401

            # 3. Verify Hash
            if not check_password_hash(device.api_key_hash, api_key):
                return jsonify({"error": "Invalid Key", "message": "API Key incorrect"}), 403

            # 4. Check Role (if specific role required)
            if required_role and device.device_role != required_role:
                return jsonify({
                    "error": "Unauthorized Role", 
                    "message": f"This endpoint requires '{required_role}' role."
                }), 403

            # 5. Attach to global context for the route to use
            g.device = device
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator