"""
notification_handler.py

Lambda function triggered by: SQS "notification-queue"
(which is subscribed to the BookingCreated SNS topic)

Responsibilities:
  1. Read the booking event from the SQS message
  2. "Send" a guest notification (simulated here via SES-style logging;
     swap in ses.send_email(...) for real email delivery)
  3. Record the notification in DynamoDB for audit/history purposes

Cloud services used programmatically here: SQS (trigger), Lambda,
DynamoDB. SNS is used upstream to fan out to this queue.
"""

import json
import os
from datetime import datetime

import boto3

dynamodb = boto3.resource("dynamodb")
NOTIFICATIONS_TABLE = os.environ["NOTIFICATIONS_TABLE"]
notifications_table = dynamodb.Table(NOTIFICATIONS_TABLE)


def _send_guest_notification(booking: dict) -> None:
    """
    Placeholder for actual guest communication (SES email / SMS via SNS).
    Kept simple and explicit so it's easy to demo and explain in the
    video walkthrough.
    """
    message = (
        f"Hi {booking['guest_name']}, your booking {booking['booking_id']} "
        f"for a {booking['room_type']} room on {booking['checkin_date']} "
        f"is confirmed at {booking['price_per_night']}/night."
    )
    print(f"[NOTIFY] {message}")


def handler(event, context):
    processed = 0
    failures = []

    for record in event.get("Records", []):
        try:
            sns_envelope = json.loads(record["body"])
            booking = json.loads(sns_envelope["Message"])

            _send_guest_notification(booking)

            notifications_table.put_item(Item={
                "notification_id": f"{booking['booking_id']}-confirmation",
                "booking_id": booking["booking_id"],
                "channel": "EMAIL",
                "sent_at": datetime.utcnow().isoformat(),
                "status": "SENT",
            })
            processed += 1

        except Exception as e:
            failures.append({"messageId": record.get("messageId"), "error": str(e)})

    # Returning batchItemFailures lets SQS retry only the failed messages,
    # not the whole batch - relevant if this is wired up with partial
    # batch response enabled on the event source mapping.
    return {
        "processed": processed,
        "batchItemFailures": [{"itemIdentifier": f["messageId"]} for f in failures],
    }
