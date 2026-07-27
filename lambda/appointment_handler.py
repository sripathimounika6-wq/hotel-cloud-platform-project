"""
appointment_handler.py

Lambda function behind: POST /appointments  (via API Gateway)

Responsibilities:
  1. Read the requested vehicle/service details from the API request body
  2. Compute the current bay occupancy for that service type/day from DynamoDB
  3. Use VehicleServiceRulesEngine.LaborPricingEngine to compute the price
  4. Write the appointment to DynamoDB
  5. Generate a simple service confirmation/work-order document and store it in S3
  6. Publish an "AppointmentCreated" event to SNS, which fans out to
     the customer notification queue (SQS)

Cloud services used programmatically here: API Gateway (trigger),
Lambda (this function), DynamoDB, S3, SNS.
"""

import json
import os
import uuid
from datetime import datetime, date

import boto3

# The custom library is bundled into the Lambda deployment package under
# a vendored directory (see README for packaging instructions).
from vehicle_service_engine import LaborPricingEngine, BlendedPricing

dynamodb = boto3.resource("dynamodb")
s3 = boto3.client("s3")
sns = boto3.client("sns")

APPOINTMENTS_TABLE = os.environ["APPOINTMENTS_TABLE"]
BAYS_TABLE = os.environ["BAYS_TABLE"]
DOCS_BUCKET = os.environ["DOCS_BUCKET"]
APPOINTMENT_TOPIC_ARN = os.environ["APPOINTMENT_TOPIC_ARN"]

appointments_table = dynamodb.Table(APPOINTMENTS_TABLE)
bays_table = dynamodb.Table(BAYS_TABLE)

pricing_engine = LaborPricingEngine(BlendedPricing())

CORS_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Allow-Methods": "OPTIONS,POST",
}


def _get_bay_occupancy_pct(service_type: str, appointment_date: str) -> float:
    """
    Look up current bay occupancy for a service type on a given day.
    Bays table stores total_bays and booked_bays counters per
    (service_type, date) - updated by this handler on each successful booking.
    """
    resp = bays_table.get_item(
        Key={"service_type": service_type, "date": appointment_date}
    )
    item = resp.get("Item")
    if not item:
        return 0.0
    total = int(item.get("total_bays", 1))
    booked = int(item.get("booked_bays", 0))
    return booked / total if total else 0.0


def _generate_work_order_document(appointment: dict) -> str:
    """
    Creates a simple text-based work order / service confirmation
    document and uploads it to S3, returning the S3 key.
    """
    content = (
        f"Service Work Order\n"
        f"===================\n"
        f"Appointment ID: {appointment['appointment_id']}\n"
        f"Customer: {appointment['customer_name']}\n"
        f"Vehicle registration: {appointment['vehicle_reg']}\n"
        f"Service type: {appointment['service_type']}\n"
        f"Appointment date: {appointment['appointment_date']}\n"
        f"Labor price: {appointment['price']}\n\n"
        f"Please drop off the vehicle by 8:30 AM on the appointment date. "
        f"A courtesy vehicle can be requested at check-in if available.\n"
    )
    key = f"work-orders/{appointment['appointment_id']}.txt"
    s3.put_object(
        Bucket=DOCS_BUCKET,
        Key=key,
        Body=content.encode("utf-8"),
        ContentType="text/plain",
    )
    return key


def handler(event, context):
    try:
        body = json.loads(event.get("body") or "{}")

        customer_name = body["customer_name"]
        vehicle_reg = body["vehicle_reg"]
        service_type = body["service_type"]
        appointment_date = body["appointment_date"]   # "YYYY-MM-DD"
        base_rate = float(body["base_rate"])
        cancellation_policy_name = body.get("cancellation_policy", "STANDARD")

        appt_dt = datetime.strptime(appointment_date, "%Y-%m-%d").date()
        days_until_appointment = (appt_dt - date.today()).days
        is_peak_day = appt_dt.weekday() == 0  # Monday is peak demand day

        bay_occupancy_pct = _get_bay_occupancy_pct(service_type, appointment_date)

        price = pricing_engine.price_for(
            base_rate=base_rate,
            bay_occupancy_pct=bay_occupancy_pct,
            days_until_appointment=max(days_until_appointment, 0),
            is_peak_day=is_peak_day,
        )

        appointment_id = str(uuid.uuid4())
        appointment = {
            "appointment_id": appointment_id,
            "customer_name": customer_name,
            "vehicle_reg": vehicle_reg,
            "service_type": service_type,
            "appointment_date": appointment_date,
            "price": str(price),
            "cancellation_policy": cancellation_policy_name,
            "status": "CONFIRMED",
            "created_at": datetime.utcnow().isoformat(),
        }

        appointments_table.put_item(Item=appointment)

        bays_table.update_item(
            Key={"service_type": service_type, "date": appointment_date},
            UpdateExpression="ADD booked_bays :inc",
            ExpressionAttributeValues={":inc": 1},
        )

        doc_key = _generate_work_order_document(appointment)
        appointment["work_order_key"] = doc_key

        sns.publish(
            TopicArn=APPOINTMENT_TOPIC_ARN,
            Message=json.dumps(appointment),
            MessageAttributes={
                "event_type": {"DataType": "String", "StringValue": "AppointmentCreated"}
            },
        )

        return {
            "statusCode": 201,
            "headers": CORS_HEADERS,
            "body": json.dumps(appointment),
        }

    except KeyError as e:
        return {
            "statusCode": 400,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": f"Missing required field: {e}"}),
        }
    except Exception as e:
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": str(e)}),
        }
