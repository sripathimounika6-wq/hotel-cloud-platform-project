"""
housekeeping_handler.py

Lambda function behind: POST /requests  (via API Gateway)

Guests submit housekeeping/room-service requests. This handler writes
the request to DynamoDB and pushes it onto an SQS queue that staff-side
tooling (or a staff mobile app, out of scope here) polls for new tasks.

Cloud services used programmatically here: API Gateway (trigger),
Lambda, DynamoDB, SQS.
"""

import json
import os
import uuid
from datetime import datetime

import boto3

dynamodb = boto3.resource("dynamodb")
sqs = boto3.client("sqs")

REQUESTS_TABLE = os.environ["REQUESTS_TABLE"]
HOUSEKEEPING_QUEUE_URL = os.environ["HOUSEKEEPING_QUEUE_URL"]

requests_table = dynamodb.Table(REQUESTS_TABLE)

VALID_REQUEST_TYPES = {"CLEANING", "TOWELS", "ROOM_SERVICE", "MAINTENANCE"}


def handler(event, context):
    try:
        body = json.loads(event.get("body") or "{}")

        booking_id = body["booking_id"]
        request_type = body["request_type"].upper()
        notes = body.get("notes", "")

        if request_type not in VALID_REQUEST_TYPES:
            return {
                "statusCode": 400,
                "body": json.dumps({
                    "error": f"request_type must be one of {sorted(VALID_REQUEST_TYPES)}"
                }),
            }

        request_id = str(uuid.uuid4())
        item = {
            "request_id": request_id,
            "booking_id": booking_id,
            "request_type": request_type,
            "notes": notes,
            "status": "PENDING",
            "created_at": datetime.utcnow().isoformat(),
        }

        requests_table.put_item(Item=item)

        sqs.send_message(
            QueueUrl=HOUSEKEEPING_QUEUE_URL,
            MessageBody=json.dumps(item),
            MessageAttributes={
                "request_type": {"DataType": "String", "StringValue": request_type}
            },
        )

        return {
            "statusCode": 201,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(item),
        }

    except KeyError as e:
        return {"statusCode": 400, "body": json.dumps({"error": f"Missing field: {e}"})}
    except Exception as e:
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}
