from flask import Blueprint, request, jsonify, g
from ..middleware.api_key import require_device_key
from ..services.epcis_client import EPCISService
from ..services.aggregation import AggregationService


events_bp = Blueprint('events', __name__)

@events_bp.route('/capture', methods=['POST'])
@require_device_key()  # Requires X-Device-Id and X-Device-Key
def capture_event():
    """
    Primary endpoint for Line Controllers to push EPCIS events.
    Supports single event or a list of events (for offline sync).
    """
    payload = request.get_json()
    if not payload:
        return jsonify({"error": "No data", "message": "Empty payload"}), 400

    # Determine if it's a single event or a list (batch sync from offline mode)
    events_to_process = []
    if isinstance(payload, list):
        events_to_process = payload
    elif isinstance(payload, dict):
        events_to_process = [payload]
    else:
        return jsonify({"error": "Invalid Format", "message": "Payload must be JSON object or array"}), 400

    processed_count = 0
    errors = []

    for event in events_to_process:
        try:
            # Optional: Enforce that the 'readPoint' matches the device's plant
            # This prevents a hacked device in Plant A from recording events for Plant B
            # (Commented out for now, but good practice for later)
            # if g.device.plant.gln not in event.get('readPoint', ''):
            #     raise ValueError("Device GLN mismatch")

            EPCISService.capture_event(event)
            processed_count += 1
        except Exception as e:
            # In a batch sync, we might not want to fail ALL events if one is bad.
            # We log the error and continue.
            errors.append({
                "event_index": events_to_process.index(event),
                "error": str(e)
            })

    response_code = 200
    if errors:
        response_code = 207  # Multi-Status (some succeeded, some failed)
    
    return jsonify({
        "message": f"Processed {processed_count} events",
        "errors": errors
    }), response_code


@events_bp.route('/trace/<path:epc>', methods=['GET'])
@require_device_key() # Or JWT if you want humans to access this specific route
def trace_epc(epc):
    """
    Simple traceability lookup for a device (e.g., a scanner checking status).
    For full human UI traceability, we'd put that in a different route.
    """
    # Use the EPCState table for instant lookup
    from ..models import db, EPCState
    
    state = db.session.get(EPCState, epc)
    if not state:
        return jsonify({"found": False, "epc": epc}), 404
        
    return jsonify({
        "found": True,
        "epc": state.epc,
        "parent": state.parent_epc,
        "status": state.current_disposition,
        "location": state.current_biz_location,
        "last_seen": state.last_event_time.isoformat() if state.last_event_time else None
    }), 200


@events_bp.route('/aggregate', methods=['POST'])
@require_device_key(required_role='line_controller')
def aggregate_batch():
    """
    Helper endpoint for Line Controllers to form batches.
    Payload: {
        "parent_epc": "urn:epc:id:sgtin:...",
        "child_epcs": ["urn:epc:id:sgtin:...", ...],
        "location": "urn:epc:id:sgln:..."
    }
    """
    data = request.get_json()
    parent = data.get('parent_epc')
    children = data.get('child_epcs')
    location = data.get('location') # or derive from g.device.plant.gln

    if not parent or not children:
        return jsonify({"error": "Missing parent or children"}), 400

    try:
        AggregationService.pack_items(parent, children, location)
        return jsonify({"message": "Aggregation successful"}), 201
    except ValueError as e:
        return jsonify({"error": "Validation Error", "message": str(e)}), 409
    except Exception as e:
        return jsonify({"error": "System Error", "details": str(e)}), 500