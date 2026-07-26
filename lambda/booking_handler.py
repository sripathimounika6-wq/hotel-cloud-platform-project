"""
booking_handler.py

Lambda function behind: POST /bookings  (via API Gateway)

Responsibilities:
  1. Read the requested room/dates from the API request body
  2. Compute the current occupancy for that room type/night from DynamoDB
  3. Use BookingRulesEngine.PricingEngine to compute the nightly price
  4. Write the booking to DynamoDB
  5. Generate a simple check-in confirmation document and store it in S3
  6. Publish a "BookingCreated" event to SNS, which fans out to:
       - the check-in automation queue (SQS)
       - the notification queue (SQS)

Cloud services used programmatically here: API Gateway (trigger),
Lambda (this function), DynamoDB, S3, SNS.
"""

import json
import os
import uuid
from datetime import datetime, date, timedelta

import boto3

# The custom library is bundled into the Lambda deployment package under
# a "vendor" directory (see infra/README for packaging instructions).
from booking_rules_engine import PricingEngine, BlendedPricing

dynamodb = boto3.resource("dynamodb")
s3 = boto3.client("s3")
sns = boto3.client("sns")

BOOKINGS_TABLE = os.environ["BOOKINGS_TABLE"]
ROOMS_TABLE = os.environ["ROOMS_TABLE"]
DOCS_BUCKET = os.environ["DOCS_BUCKET"]
BOOKING_TOPIC_ARN = os.environ["BOOKING_TOPIC_ARN"]

bookings_table = dynamodb.Table(BOOKINGS_TABLE)
rooms_table = dynamodb.Table(ROOMS_TABLE)

pricing_engine = PricingEngine(BlendedPricing())


def _get_occupancy_pct(room_type: str, checkin_date: str) -> float:
    """
    Look up current occupancy for a room type on a given night.
    Rooms table stores total_rooms and booked_rooms counters per
    (room_type, date) - updated by this handler on each successful booking.
    """
    resp = rooms_table.get_item(
        Key={"room_type": room_type, "date": checkin_date}
    )
    item = resp.get("Item")
    if not item:
        return 0.0
    total = int(item.get("total_rooms", 1))
    booked = int(item.get("booked_rooms", 0))
    return booked / total if total else 0.0


def _generate_checkin_document(booking: dict) -> str:
    """
    Creates a simple text-based check-in instructions document and
    uploads it to S3, returning the S3 key.
    """
    content = (
        f"Check-in instructions\n"
        f"======================\n"
        f"Booking ID: {booking['booking_id']}\n"
        f"Guest: {booking['guest_name']}\n"
        f"Room type: {booking['room_type']}\n"
        f"Check-in date: {booking['checkin_date']}\n"
        f"Price/night: {booking['price_per_night']}\n\n"
        f"Please present a photo ID at reception. Self check-in kiosks "
        f"are available in the lobby from 3:00 PM.\n"
    )
    key = f"checkin-docs/{booking['booking_id']}.txt"
    s3.put_object(
        Bucket=DOCS_BUCKET,
        Key=key,
        Body=content.encode("utf-8"),
        ContentType="text/plain",
    )
    return key


def handler(event, context):
    try:
        body = json.loads(event.get("body") or "{}")

        guest_name = body["guest_name"]
        room_type = body["room_type"]
        checkin_date = body["checkin_date"]      # "YYYY-MM-DD"
        base_rate = float(body["base_rate"])
        cancellation_policy_name = body.get("cancellation_policy", "MODERATE")

        checkin_dt = datetime.strptime(checkin_date, "%Y-%m-%d").date()
        days_until_checkin = (checkin_dt - date.today()).days
        is_weekend = checkin_dt.weekday() in (4, 5)  # Fri/Sat night stays

        occupancy_pct = _get_occupancy_pct(room_type, checkin_date)

        price = pricing_engine.price_for(
            base_rate=base_rate,
            occupancy_pct=occupancy_pct,
            days_until_checkin=max(days_until_checkin, 0),
            is_weekend=is_weekend,
        )

        booking_id = str(uuid.uuid4())
        booking = {
            "booking_id": booking_id,
            "guest_name": guest_name,
            "room_type": room_type,
            "checkin_date": checkin_date,
            "price_per_night": str(price),
            "cancellation_policy": cancellation_policy_name,
            "status": "CONFIRMED",
            "created_at": datetime.utcnow().isoformat(),
        }

        bookings_table.put_item(Item=booking)

        rooms_table.update_item(
            Key={"room_type": room_type, "date": checkin_date},
            UpdateExpression="ADD booked_rooms :inc",
            ExpressionAttributeValues={":inc": 1},
        )

        doc_key = _generate_checkin_document(booking)
        booking["checkin_doc_key"] = doc_key

        sns.publish(
            TopicArn=BOOKING_TOPIC_ARN,
            Message=json.dumps(booking),
            MessageAttributes={
                "event_type": {"DataType": "String", "StringValue": "BookingCreated"}
            },
        )

        return {
            "statusCode": 201,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(booking),
        }

    except KeyError as e:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": f"Missing required field: {e}"}),
        }
    except Exception as e:
        # In production this would also emit a structured log / metric
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)}),
        }
