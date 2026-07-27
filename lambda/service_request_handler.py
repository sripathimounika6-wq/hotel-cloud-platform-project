"""
service_request_handler.py

Lambda function behind: POST /requests  (via API Gateway)

Customers submit additional service requests against an existing
appointment (e.g. request a courtesy vehicle, an extra inspection, or
pickup/drop-off). This handler writes the request to DynamoDB and
pushes it onto an SQS queue that the service center's staff tooling
polls for new tasks.

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
SERVICE_REQUEST_QUEUE_URL = os.environ["SERVICE_REQUEST_QUEUE_URL"]

requests_table = dynamodb.Table(REQUESTS_TABLE)

VALID_REQUEST_TYPES = {"COURTESY_VEHICLE", "EXTRA_INSPECTION", "PICKUP_DROPOFF", "PARTS_ORDER"}

CORS_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Allow-Methods": "OPTIONS,POST",
}


def handler(event, context):
    try:
        body = json.loads(event.get("body") or "{}")

        appointment_id = body["appointment_id"]
        request_type = body["request_type"].upper()
        notes = body.get("notes", "")

        if request_type not in VALID_REQUEST_TYPES:
            return {
                "statusCode": 400,
                "headers": CORS_HEADERS,
                "body": json.dumps({
                    "error": f"request_type must be one of {sorted(VALID_REQUEST_TYPES)}"
                }),
            }

        request_id = str(uuid.uuid4())
        item = {
            "request_id": request_id,
            "appointment_id": appointment_id,
            "request_type": request_type,
            "notes": notes,
            "status": "PENDING",
            "created_at": datetime.utcnow().isoformat(),
        }

        requests_table.put_item(Item=item)

        sqs.send_message(
            QueueUrl=SERVICE_REQUEST_QUEUE_URL,
            MessageBody=json.dumps(item),
            MessageAttributes={
                "request_type": {"DataType": "String", "StringValue": request_type}
            },
        )

        return {
            "statusCode": 201,
            "headers": CORS_HEADERS,
            "body": json.dumps(item),
        }

    except KeyError as e:
        return {
            "statusCode": 400,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": f"Missing field: {e}"}),
        }
    except Exception as e:
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": str(e)}),
        }
