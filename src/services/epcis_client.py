from datetime import datetime, timezone
from sqlalchemy.exc import IntegrityError
from ..models import db, EPCISEvent, EPCState

class EPCISService:
    """
    Handles the core logic for capturing EPCIS 2.0 events and 
    maintaining the current state of items (Digital Twin).
    """

    @staticmethod
    def capture_event(event_data: dict):
        """
        Main entry point for recording events.
        Determines event type and delegates logic.
        """
        event_type = event_data.get('type')
        
        try:
            if event_type == 'ObjectEvent':
                return EPCISService._handle_object_event(event_data)
            elif event_type == 'AggregationEvent':
                return EPCISService._handle_aggregation_event(event_data)
            else:
                raise ValueError(f"Unsupported event type: {event_type}")
        except Exception as e:
            db.session.rollback()
            raise e

    @staticmethod
    def _handle_object_event(data: dict):
        """
        Handles Commissioning (Birth), Shipping, Receiving, Scanning.
        """
        # 1. Create the Immutable History Record
        # We assume data['eventTime'] comes in ISO format or we default to now
        event_time = data.get('eventTime') or datetime.now(timezone.utc)
        
        new_event = EPCISEvent(
            event_type="ObjectEvent",
            action=data.get('action', 'OBSERVE'),
            event_time=event_time,
            event_timezone_offset=data.get('eventTimeZoneOffset', '+00:00'),
            biz_step=data.get('bizStep'),
            disposition=data.get('disposition'),
            read_point=data.get('readPoint'),
            biz_location=data.get('bizLocation'),
            data=data  # Store full JSON payload for flexibility
        )
        db.session.add(new_event)

        # 2. Update the "Current State" (Digital Twin)
        # ObjectEvents usually affect a list of EPCs (epcList)
        epc_list = data.get('epcList', [])
        
        for epc in epc_list:
            # Upsert logic (Insert if new, Update if exists)
            state = db.session.get(EPCState, epc)
            if not state:
                state = EPCState(epc=epc)
                db.session.add(state)
            
            # Update state fields
            state.last_event_time = event_time
            if data.get('bizLocation'):
                state.current_biz_location = data['bizLocation']
            if data.get('disposition'):
                state.current_disposition = data['disposition']

        db.session.commit()
        return new_event

    @staticmethod
    def _handle_aggregation_event(data: dict):
        """
        Handles Packing (Items -> Batch, Batches -> Mastercase).
        """
        parent_id = data.get('parentID')
        child_epcs = data.get('childEPCs', [])
        action = data.get('action', 'ADD')
        event_time = data.get('eventTime') or datetime.now(timezone.utc)

        # 1. Create History Record
        new_event = EPCISEvent(
            event_type="AggregationEvent",
            action=action,
            event_time=event_time,
            event_timezone_offset=data.get('eventTimeZoneOffset', '+00:00'),
            biz_step=data.get('bizStep'),
            disposition=data.get('disposition'),
            read_point=data.get('readPoint'),
            biz_location=data.get('bizLocation'),
            data=data
        )
        db.session.add(new_event)

        # 2. Update State (Parent-Child Relationships)
        if action == 'ADD':
            # Parent State
            parent_state = db.session.get(EPCState, parent_id)
            if not parent_state:
                parent_state = EPCState(epc=parent_id)
                db.session.add(parent_state)
            
            parent_state.last_event_time = event_time
            parent_state.current_disposition = data.get('disposition')

            # Children State
            for child_epc in child_epcs:
                child_state = db.session.get(EPCState, child_epc)
                if not child_state:
                    # Should technically exist if commissioned, but auto-create for robustness
                    child_state = EPCState(epc=child_epc)
                    db.session.add(child_state)
                
                # The critical link: Point child to parent
                child_state.parent_epc = parent_id
                child_state.last_event_time = event_time
                # Children inherit location of the aggregation event
                if data.get('bizLocation'):
                    child_state.current_biz_location = data['bizLocation']

        elif action == 'DELETE':
            # Disaggregation (Unpacking)
            for child_epc in child_epcs:
                child_state = db.session.get(EPCState, child_epc)
                if child_state:
                    child_state.parent_epc = None
                    child_state.last_event_time = event_time

        db.session.commit()
        return new_event