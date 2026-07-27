# Ironclad Auto — Fleet Vehicle Service & Maintenance Booking Platform
Automotive sector — Cloud Platform Programming project (AWS)

## 1. What this is

A serverless vehicle service booking backend. Customers book a service
bay slot for their vehicle (oil change, full service, diagnostic,
repair) with labor pricing that reflects real bay occupancy, and submit
additional service requests (courtesy vehicle, extra inspection,
pickup/drop-off, parts order). A booking automatically triggers work
order generation and a customer notification via an event-driven
pipeline.

## 2. Architecture

```
Customer
      │
      ▼
API Gateway  ──POST /appointments──▶ AppointmentFunction (Lambda)
      │                                    │
      │                                    ├─▶ DynamoDB (Appointments, Bays)
      │                                    ├─▶ S3 (work order document)
      │                                    └─▶ SNS "AppointmentCreated" topic
      │                                              │
      │                                              ▼
      │                                       SQS NotificationQueue
      │                                              │
      │                                              ▼
      │                                     NotificationFunction (Lambda)
      │                                              │
      │                                              ▼
      │                                     DynamoDB (Notifications)
      │
      └──POST /requests──▶ ServiceRequestFunction (Lambda)
                                  │
                                  ├─▶ DynamoDB (Requests)
                                  └─▶ SQS ServiceRequestQueue (staff tooling polls this)
```

**Pattern used:** event-driven / fan-out via pub-sub (SNS → SQS),
decoupling appointment creation from downstream notification
processing — the NotificationFunction can fail/retry independently of
the booking API call succeeding.

**Cloud services used programmatically (6, exceeds the 5 required):**
1. API Gateway — REST trigger for both customer-facing Lambdas
2. Lambda — all three functions
3. DynamoDB — 4 tables (Appointments, Bays, Requests, Notifications)
4. S3 — work order document storage (object storage requirement)
5. SNS — AppointmentCreated event topic (pub/sub requirement)
6. SQS — notification queue + service request queue (pub/sub requirement)

## 3. Custom library: `vehicle_service_engine`

Located in `lib/vehicle_service_engine/`. Pure Python, no AWS
dependency, fully unit tested (`tests/test_vehicle_service_engine.py`).

| Module | Purpose |
|---|---|
| `cancellation_policy.py` | Strategy pattern: FLEXIBLE / STANDARD / NO_SHOW_STRICT deposit refund rules |
| `labor_pricing.py` | Strategy pattern: occupancy-based + last-minute dynamic labor pricing |
| `bay_allocation_resolver.py` | Prioritises which appointments keep their bay slot when overbooked, by customer tier (fleet accounts protected first) |

`appointment_handler.py` imports `LaborPricingEngine` to compute the
service price — this is the "meaningful functionality" the library
provides to the application.

Run tests locally:
```bash
python -m pytest tests/ -v
```

## 4. Deployment (manual AWS Console + CLI)

**Step 1 — S3 buckets**
- One private bucket for work-order documents
- One public bucket with static website hosting enabled, for the frontend

**Step 2 — DynamoDB tables**
| Table | Partition key | Sort key |
|---|---|---|
| `Appointments` | `appointment_id` (String) | — |
| `Bays` | `service_type` (String) | `date` (String) |
| `Requests` | `request_id` (String) | — |
| `Notifications` | `notification_id` (String) | — |

**Step 3 — SNS topic + SQS queues**
Topic `AppointmentCreatedTopic`; queues `NotificationQueue` and
`ServiceRequestQueue`; subscribe `NotificationQueue` to the topic.

**Step 4 — Lambda functions**
Python 3.12 runtime, execution role = your account's existing Lambda
role (e.g. `LabRole` in an AWS Academy Lab):

- `AppointmentFunction` — upload `appointment_function.zip` (handler +
  vendored `vehicle_service_engine` library), handler:
  `appointment_handler.handler`, env vars:
  - `APPOINTMENTS_TABLE=Appointments`
  - `BAYS_TABLE=Bays`
  - `DOCS_BUCKET=<your-docs-bucket-name>`
  - `APPOINTMENT_TOPIC_ARN=<AppointmentCreatedTopic ARN>`
- `ServiceRequestFunction` — upload `service_request_function.zip`,
  handler: `service_request_handler.handler`, env vars:
  - `REQUESTS_TABLE=Requests`
  - `SERVICE_REQUEST_QUEUE_URL=<ServiceRequestQueue URL>`
- `NotificationFunction` — upload `notification_function.zip`, handler:
  `notification_handler.handler`, env vars:
  - `NOTIFICATIONS_TABLE=Notifications`

**Step 5 — Wire NotificationQueue → NotificationFunction**
Add an SQS trigger on `NotificationFunction` pointing at `NotificationQueue`.

**Step 6 — API Gateway**
REST API `FleetApi` with:
- `POST /appointments` → `AppointmentFunction` (Lambda proxy integration)
- `POST /requests` → `ServiceRequestFunction` (Lambda proxy integration)

Enable CORS on **both resources** (Actions → Enable CORS → check POST +
OPTIONS → Allow-Origin `*`), then also add **Method Response** entries
for status codes `201`, `400`, and `500` on each POST method with the
same 3 CORS headers (`Access-Control-Allow-Origin`,
`Access-Control-Allow-Headers`, `Access-Control-Allow-Methods`) —
Lambda proxy integration only passes headers through for status codes
explicitly declared in Method Response. Deploy to a `prod` stage.

**Step 7 — Upload the frontend**
```bash
aws s3 cp frontend/index.html s3://<your-frontend-bucket>/index.html
aws s3 website s3://<your-frontend-bucket>/ --index-document index.html
aws s3api put-bucket-policy --bucket <your-frontend-bucket> --policy file://bucket-policy.json
```
Then edit the "API endpoint" field at the bottom of the page (or the
default value in `index.html`) to your deployed API's invoke URL.

**Step 8 — Seed a bay occupancy record**
```bash
aws dynamodb put-item \
  --table-name Bays \
  --item '{"service_type":{"S":"Full Service"},"date":{"S":"2026-08-15"},"total_bays":{"N":"6"},"booked_bays":{"N":"4"}}'
```

**Step 9 — Test**
Open the frontend's S3 website URL, submit the booking form, then use
the returned `appointment_id` in the request form. Or via CLI:
```bash
curl -X POST "<api-invoke-url>/appointments" \
  -H "Content-Type: application/json" \
  -d '{"customer_name":"Jane Doe","vehicle_reg":"13-D-45678","service_type":"Full Service","appointment_date":"2026-08-15","base_rate":120.00,"cancellation_policy":"STANDARD"}'
```

**Step 10 — Verify the pipeline**
- `Appointments` and `Bays` tables updated
- `work-orders/<appointment_id>.txt` present in the docs bucket
- CloudWatch Logs for `NotificationFunction` show a `[NOTIFY] ...` line
- `Notifications` table has a new item

## 5. Project structure

```
fleet-cloud-project/
├── frontend/index.html
├── lambda/
│   ├── appointment_handler.py
│   ├── service_request_handler.py
│   ├── notification_handler.py
│   └── vehicle_service_engine/     (vendored copy of lib/)
├── lib/vehicle_service_engine/     (source of truth for the library)
│   ├── __init__.py
│   ├── cancellation_policy.py
│   ├── labor_pricing.py
│   └── bay_allocation_resolver.py
└── tests/test_vehicle_service_engine.py
```

## 6. Tearing down (only after grading)
Delete the Lambda functions, API Gateway, DynamoDB tables, SNS topic,
SQS queues, and S3 buckets via the console or `aws` CLI.
