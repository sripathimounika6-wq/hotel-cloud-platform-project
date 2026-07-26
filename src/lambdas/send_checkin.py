"""
send_checkin.py

Triggered by: SQS (CheckInQueue), which receives messages fanned out
from the BookingEvents SNS topic (filtered to BOOKING_CONFIRMED).

Uses:
  - S3 (GuestDocsBucket) -> stores the generated check-in instructions
  - DynamoDB (BookingsTable) -> reads booking details for the PDF content

This demonstrates the pub/sub -> serverless -> object storage chain:
booking event -> SNS -> SQS -> Lambda -> S3.
"""

import json
import os
import boto3

s3 = boto3.client("s3")
dynamodb = boto3.resource("dynamodb")
bookings_table = dynamodb.Table(os.environ["BOOKINGS_TABLE"])
BUCKET = os.environ["DOCS_BUCKET"]


def handler(event, context):
    for record in event["Records"]:
        # SNS-to-SQS messages wrap the original payload inside "Message"
        sns_envelope = json.loads(record["body"])
        booking = json.loads(sns_envelope["Message"])

        checkin_text = _build_checkin_document(booking)
        key = f"checkins/{booking['bookingId']}.txt"

        s3.put_object(
            Bucket=BUCKET,
            Key=key,
            Body=checkin_text.encode("utf-8"),
            ContentType="text/plain",
        )

    return {"statusCode": 200}


def _build_checkin_document(booking: dict) -> str:
    return (
        f"Check-in Instructions\n"
        f"----------------------\n"
        f"Booking ID: {booking['bookingId']}\n"
        f"Guest: {booking['guestId']}\n"
        f"Room: {booking['roomId']}\n"
        f"Check-in date: {booking['checkinDate']}\n"
        f"Please use the self-service kiosk in the lobby with this "
        f"booking ID, or present it at reception.\n"
    )
