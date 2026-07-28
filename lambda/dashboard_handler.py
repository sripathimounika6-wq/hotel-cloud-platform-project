"""
dashboard_handler.py

Lambda function behind: GET /dashboard  (via API Gateway)

Staff-only endpoint. Requires a valid session token (from
auth_login_handler) in the Authorization header. Scans the
Appointments and Requests tables and returns aggregate counts for the
staff dashboard: total appointments, breakdown by service type and
status, total service requests, and breakdown by request type.

This is a simple read-side aggregation, deliberately done with table
scans since the dataset size in this project is small; a production
system at scale would instead maintain running counters (e.g. via a
DynamoDB Streams + Lambda pattern) rather than scanning on every
dashboard load.

Cloud services used programmatically here: API Gateway (trigger),
Lambda, DynamoDB.
"""

import json
import os
from collections import Counter

import boto3

from session_utils import get_valid_session, extract_bearer_token

dynamodb = boto3.resource("dynamodb")
APPOINTMENTS_TABLE = os.environ["APPOINTMENTS_TABLE"]
REQUESTS_TABLE = os.environ["REQUESTS_TABLE"]
SESSIONS_TABLE = os.environ["SESSIONS_TABLE"]

appointments_table = dynamodb.Table(APPOINTMENTS_TABLE)
requests_table = dynamodb.Table(REQUESTS_TABLE)
sessions_table = dynamodb.Table(SESSIONS_TABLE)

CORS_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
    "Access-Control-Allow-Methods": "OPTIONS,GET",
}


def _scan_all(table):
    """Paginates through a full table scan and returns every item."""
    items = []
    resp = table.scan()
    items.extend(resp.get("Items", []))
    while "LastEvaluatedKey" in resp:
        resp = table.scan(ExclusiveStartKey=resp["LastEvaluatedKey"])
        items.extend(resp.get("Items", []))
    return items


def handler(event, context):
    try:
        token = extract_bearer_token(event)
        session = get_valid_session(sessions_table, token)
        if not session:
            return {
                "statusCode": 401,
                "headers": CORS_HEADERS,
                "body": json.dumps({"error": "Invalid or expired session"}),
            }

        appointments = _scan_all(appointments_table)
        requests_ = _scan_all(requests_table)

        service_type_counts = Counter(a.get("service_type", "Unknown") for a in appointments)
        appointment_status_counts = Counter(a.get("status", "Unknown") for a in appointments)
        request_type_counts = Counter(r.get("request_type", "Unknown") for r in requests_)
        request_status_counts = Counter(r.get("status", "Unknown") for r in requests_)

        summary = {
            "total_appointments": len(appointments),
            "total_requests": len(requests_),
            "appointments_by_service_type": dict(service_type_counts),
            "appointments_by_status": dict(appointment_status_counts),
            "requests_by_type": dict(request_type_counts),
            "requests_by_status": dict(request_status_counts),
        }

        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps(summary),
        }

    except Exception as e:
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": str(e)}),
        }
