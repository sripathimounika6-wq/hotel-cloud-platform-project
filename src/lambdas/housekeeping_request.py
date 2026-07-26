"""
housekeeping_request.py

Triggered by: API Gateway POST /housekeeping
Uses: SNS (BookingEventsTopic) -> publishes HOUSEKEEPING_REQUESTED event,
which the SNS filter policy routes only to HousekeepingQueue (not
CheckInQueue). This is the second branch of the fan-out pattern.
"""

import json
import os
import boto3
from datetime import datetime

sns = boto3.client("sns")
TOPIC_ARN = os.environ["BOOKING_EVENTS_TOPIC"]


def handler(event, context):
    body = json.loads(event["body"])
    booking_id = body["bookingId"]
    request_type = body.get("requestType", "general_cleaning")

    message = {
        "bookingId": booking_id,
        "requestType": request_type,
        "requestedAt": datetime.utcnow().isoformat(),
    }

    sns.publish(
        TopicArn=TOPIC_ARN,
        Message=json.dumps(message),
        MessageAttributes={
            "eventType": {"DataType": "String", "StringValue": "HOUSEKEEPING_REQUESTED"}
        },
    )

    return {
        "statusCode": 202,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"message": "Housekeeping request received", **message}),
    }
