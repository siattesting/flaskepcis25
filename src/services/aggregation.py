from datetime import datetime, timezone
from sqlalchemy import select
from ..models import db, EPCState
from .epcis_client import EPCISService

class AggregationService:
    """
    Manages the hierarchy of items (Item -> Batch -> Mastercase -> Pallet).
    Enforces physical logic before recording events.
    """

    @staticmethod
    def pack_items(parent_epc: str, child_epcs: list, biz_location: str, 
                   biz_step: str = "urn:epcglobal:cbv:bizstep:packing"):
        """
        Aggregates a list of children into a parent container.
        
        Args:
            parent_epc: The target container (e.g., LGTIN or SSCC).
            child_epcs: List of items to go inside.
            biz_location: Where this is happening (GLN).
            biz_step: The business context (default: packing).
        """
        if not child_epcs:
            raise ValueError("Cannot aggregate empty list of children")

        # --- 1. Validate Physical State (Pre-Flight Checks) ---
        
        # A. Check if children are already packed elsewhere
        # We query the State table for all children at once
        stmt = select(EPCState).where(EPCState.epc.in_(child_epcs))
        existing_states = db.session.execute(stmt).scalars().all()
        
        state_map = {s.epc: s for s in existing_states}
        
        for child in child_epcs:
            state = state_map.get(child)
            
            # If state exists, check its current parent
            if state and state.parent_epc:
                # If it's already packed in THIS parent, it's a retry/duplicate scan. Ignore it.
                if state.parent_epc == parent_epc:
                    continue 
                
                # If it's packed in a DIFFERENT parent, that's an error.
                raise ValueError(f"Item {child} is already packed in {state.parent_epc}. Unpack it first.")

            # Optional: Check if item is 'shipped' or 'inactive'
            if state and state.current_disposition == 'urn:epcglobal:cbv:disp:inactive':
                 raise ValueError(f"Item {child} is marked inactive/destroyed.")

        # --- 2. Construct the EPCIS Payload ---
        
        event_data = {
            "type": "AggregationEvent",
            "action": "ADD",
            "parentID": parent_epc,
            "childEPCs": child_epcs,
            "eventTime": datetime.now(timezone.utc).isoformat(),
            "eventTimeZoneOffset": "+00:00",
            "bizStep": biz_step,
            "disposition": "urn:epcglobal:cbv:disp:active", # Items are active inside the box
            "readPoint": biz_location,
            "bizLocation": biz_location
        }

        # --- 3. Execute Transaction via Core Service ---
        # This will write the Event AND update the EPCState table
        return EPCISService.capture_event(event_data)

    @staticmethod
    def unpack_parent(parent_epc: str, biz_location: str):
        """
        Disaggregates a parent (removes all children).
        Useful for "Rework" (fixing a bad batch).
        """
        # 1. Find who is currently inside this parent
        stmt = select(EPCState).where(EPCState.parent_epc == parent_epc)
        children = db.session.execute(stmt).scalars().all()
        
        if not children:
            return None # Nothing to unpack

        child_epcs = [c.epc for c in children]

        # 2. Construct Delete Event
        event_data = {
            "type": "AggregationEvent",
            "action": "DELETE", # EPCIS standard for unpacking
            "parentID": parent_epc,
            "childEPCs": child_epcs,
            "eventTime": datetime.now(timezone.utc).isoformat(),
            "eventTimeZoneOffset": "+00:00",
            "bizStep": "urn:epcglobal:cbv:bizstep:unpacking",
            "disposition": "urn:epcglobal:cbv:disp:active",
            "readPoint": biz_location,
            "bizLocation": biz_location
        }

        return EPCISService.capture_event(event_data)