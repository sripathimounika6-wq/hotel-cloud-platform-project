"""
auth_login_handler.py

Lambda function behind: POST /auth/login  (via API Gateway)

Validates employee credentials and issues an opaque session token.
The token is a random UUID stored in a Sessions table alongside an
expiry timestamp - the dashboard endpoint checks this table to decide
whether a request is authenticated, rather than using a self-contained
JWT (kept deliberately simple for this project's scope).

Cloud services used programmatically here: API Gateway (trigger),
Lambda, DynamoDB.
"""

import json
import os
import uuid
from datetime import datetime, timedelta

import boto3

from auth_utils import verify_password

dynamodb = boto3.resource("dynamodb")
EMPLOYEES_TABLE = os.environ["EMPLOYEES_TABLE"]
SESSIONS_TABLE = os.environ["SESSIONS_TABLE"]

employees_table = dynamodb.Table(EMPLOYEES_TABLE)
sessions_table = dynamodb.Table(SESSIONS_TABLE)

SESSION_LIFETIME_HOURS = 8

CORS_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
    "Access-Control-Allow-Methods": "OPTIONS,POST",
}


def handler(event, context):
    try:
        body = json.loads(event.get("body") or "{}")
        email = body["email"].lower().strip()
        password = body["password"]

        resp = employees_table.get_item(Key={"email": email})
        employee = resp.get("Item")

        if not employee or not verify_password(password, employee["password_hash"]):
            return {
                "statusCode": 401,
                "headers": CORS_HEADERS,
                "body": json.dumps({"error": "Invalid email or password"}),
            }

        token = str(uuid.uuid4())
        expires_at = (datetime.utcnow() + timedelta(hours=SESSION_LIFETIME_HOURS)).isoformat()

        sessions_table.put_item(Item={
            "token": token,
            "email": email,
            "expires_at": expires_at,
        })

        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps({
                "token": token,
                "name": employee.get("name", ""),
                "email": email,
                "expires_at": expires_at,
            }),
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
