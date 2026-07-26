"""
create_booking.py

Triggered by: API Gateway POST /bookings
Uses:
  - DynamoDB (BookingsTable, RoomsTable)  -> persistence
  - SNS (BookingEventsTopic)              -> publishes BOOKING_CONFIRMED event
  - booking_rules_engine (custom library) -> dynamic pricing

Flow: validate input -> look up room -> price it via PricingEngine ->
write booking to DynamoDB -> publish event to SNS so downstream
consumers (check-in Lambda) can react asynchronously.
"""

import json
import os
import uuid
import boto3
from datetime import datetime

import sys
sys.path.append("../library")
from booking_rules_engine import PricingEngine  # custom library import

dynamodb = boto3.resource("dynamodb")
sns = boto3.client("sns")

bookings_table = dynamodb.Table(os.environ["BOOKINGS_TABLE"])
rooms_table = dynamodb.Table(os.environ["ROOMS_TABLE"])
TOPIC_ARN = os.environ["BOOKING_EVENTS_TOPIC"]

pricing_engine = PricingEngine()


def handler(event, context):
    body = json.loads(event["body"])
    guest_id = body["guestId"]
    room_id = body["roomId"]
    checkin_date = body["checkinDate"]
    checkout_date = body["checkoutDate"]

    room = rooms_table.get_item(Key={"roomId": room_id}).get("Item")
    if not room:
        return _response(404, {"message": "Room not found"})

    price = pricing_engine.price_for_room(
        base_rate=float(room["baseRate"]),
        rooms_total=int(room["totalOfType"]),
        rooms_booked=int(room["currentlyBooked"]),
    )

    booking_id = str(uuid.uuid4())
    booking_item = {
        "bookingId": booking_id,
        "guestId": guest_id,
        "roomId": room_id,
        "checkinDate": checkin_date,
        "checkoutDate": checkout_date,
        "finalPrice": str(price),
        "status": "CONFIRMED",
        "createdAt": datetime.utcnow().isoformat(),
    }
    bookings_table.put_item(Item=booking_item)

    # Publish event -> fans out to CheckInQueue via SNS filter policy
    sns.publish(
        TopicArn=TOPIC_ARN,
        Message=json.dumps(booking_item),
        MessageAttributes={
            "eventType": {"DataType": "String", "StringValue": "BOOKING_CONFIRMED"}
        },
    )

    return _response(201, booking_item)


def _response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }
