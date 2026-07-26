"""
process_housekeeping.py

Triggered by: SQS (HousekeepingQueue)
Uses: DynamoDB (BookingsTable) -> records the pending housekeeping
task against the booking, so staff can query it via GetBookings.
"""

import json
import os
import boto3
from datetime import datetime

dynamodb = boto3.resource("dynamodb")
bookings_table = dynamodb.Table(os.environ["BOOKINGS_TABLE"])


def handler(event, context):
    for record in event["Records"]:
        sns_envelope = json.loads(record["body"])
        request = json.loads(sns_envelope["Message"])

        bookings_table.update_item(
            Key={"bookingId": request["bookingId"]},
            UpdateExpression="SET housekeepingStatus = :s, lastRequestType = :t, lastRequestedAt = :ts",
            ExpressionAttributeValues={
                ":s": "PENDING",
                ":t": request["requestType"],
                ":ts": datetime.utcnow().isoformat(),
            },
        )

    return {"statusCode": 200}
