"""
notification_handler.py

Lambda function triggered by: SQS "notification-queue"
(which is subscribed to the AppointmentCreated SNS topic)

Responsibilities:
  1. Read the appointment event from the SQS message
  2. "Send" a customer notification (simulated here via logging;
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


def _send_customer_notification(appointment: dict) -> None:
    """
    Placeholder for actual customer communication (SES email / SMS via
    SNS). Kept simple and explicit so it's easy to demo and explain in
    the video walkthrough.
    """
    message = (
        f"Hi {appointment['customer_name']}, your {appointment['service_type']} "
        f"appointment for vehicle {appointment['vehicle_reg']} on "
        f"{appointment['appointment_date']} is confirmed at {appointment['price']}."
    )
    print(f"[NOTIFY] {message}")


def handler(event, context):
    processed = 0
    failures = []

    for record in event.get("Records", []):
        try:
            sns_envelope = json.loads(record["body"])
            appointment = json.loads(sns_envelope["Message"])

            _send_customer_notification(appointment)

            notifications_table.put_item(Item={
                "notification_id": f"{appointment['appointment_id']}-confirmation",
                "appointment_id": appointment["appointment_id"],
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
