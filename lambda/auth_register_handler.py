"""
auth_register_handler.py

Lambda function behind: POST /auth/register  (via API Gateway)

Registers a new staff/employee account. Passwords are hashed with
PBKDF2-HMAC-SHA256 (see auth_utils.py) before being stored - the
plaintext password is never persisted.

Cloud services used programmatically here: API Gateway (trigger),
Lambda, DynamoDB.
"""

import json
import os
from datetime import datetime

import boto3

from auth_utils import hash_password

dynamodb = boto3.resource("dynamodb")
EMPLOYEES_TABLE = os.environ["EMPLOYEES_TABLE"]
employees_table = dynamodb.Table(EMPLOYEES_TABLE)

CORS_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
    "Access-Control-Allow-Methods": "OPTIONS,POST",
}


def handler(event, context):
    try:
        body = json.loads(event.get("body") or "{}")
        name = body["name"]
        email = body["email"].lower().strip()
        password = body["password"]

        if len(password) < 6:
            return {
                "statusCode": 400,
                "headers": CORS_HEADERS,
                "body": json.dumps({"error": "Password must be at least 6 characters"}),
            }

        existing = employees_table.get_item(Key={"email": email})
        if "Item" in existing:
            return {
                "statusCode": 400,
                "headers": CORS_HEADERS,
                "body": json.dumps({"error": "An account with that email already exists"}),
            }

        employees_table.put_item(Item={
            "email": email,
            "name": name,
            "password_hash": hash_password(password),
            "created_at": datetime.utcnow().isoformat(),
        })

        return {
            "statusCode": 201,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": "Account created", "email": email}),
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
