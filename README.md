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
1. API Gateway — REST trigger for all five Lambdas (customer + staff)
2. Lambda — six functions total
3. DynamoDB — 6 tables (Appointments, Bays, Requests, Notifications, Employees, Sessions)
4. S3 — work order document storage (object storage requirement)
5. SNS — AppointmentCreated event topic (pub/sub requirement)
6. SQS — notification queue + service request queue (pub/sub requirement)

## 2b. Staff portal (authentication + dashboard)

Separate from the public customer booking forms, the frontend
includes a **Staff Portal** section with three tabs:

- **Register** — creates a new employee account (`POST /auth/register`).
  Passwords are hashed with PBKDF2-HMAC-SHA256 and a random per-user
  salt (`lambda/auth_utils.py`) — the plaintext password is never
  stored.
- **Login** — validates credentials (`POST /auth/login`) and issues an
  opaque session token (a UUID stored in a `Sessions` table with an
  8-hour expiry). The token is kept in the browser's `localStorage` and
  sent as a Bearer token on subsequent requests.
- **Dashboard** — staff-only (`GET /dashboard`, validated via the
  session token) — scans the `Appointments` and `Requests` tables and
  returns aggregate counts: total appointments, breakdown by service
  type, total requests, breakdown by request type.

This is a deliberately lightweight, self-built auth system (no
Cognito) - appropriate for the project's scope, and gives you full
visibility into the auth code for the video Q&A (versus a managed
service where the mechanics are hidden).


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
| `Employees` | `email` (String) | — |
| `Sessions` | `token` (String) | — |

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
- `AuthRegisterFunction` — upload `auth_register_function.zip`
  (handler + `auth_utils.py`), handler: `auth_register_handler.handler`,
  env vars:
  - `EMPLOYEES_TABLE=Employees`
- `AuthLoginFunction` — upload `auth_login_function.zip` (handler +
  `auth_utils.py`), handler: `auth_login_handler.handler`, env vars:
  - `EMPLOYEES_TABLE=Employees`
  - `SESSIONS_TABLE=Sessions`
- `DashboardFunction` — upload `dashboard_function.zip` (handler +
  `session_utils.py`), handler: `dashboard_handler.handler`, env vars:
  - `APPOINTMENTS_TABLE=Appointments`
  - `REQUESTS_TABLE=Requests`
  - `SESSIONS_TABLE=Sessions`

**Step 5 — Wire NotificationQueue → NotificationFunction**
Add an SQS trigger on `NotificationFunction` pointing at `NotificationQueue`.

**Step 6 — API Gateway**
REST API `FleetApi` with:
- `POST /appointments` → `AppointmentFunction` (Lambda proxy integration)
- `POST /requests` → `ServiceRequestFunction` (Lambda proxy integration)
- `POST /auth/register` → `AuthRegisterFunction` (Lambda proxy integration)
- `POST /auth/login` → `AuthLoginFunction` (Lambda proxy integration)
- `GET /dashboard` → `DashboardFunction` (Lambda proxy integration)

Enable CORS on **every resource** (Actions → Enable CORS → check the
relevant methods + OPTIONS → Allow-Origin `*`; include `Authorization`
in Allow-Headers since `/dashboard` needs it). Then also add **Method
Response** entries for every status code each Lambda can return (e.g.
`200`/`201`, `400`, `401`, `500`) on each method with the same CORS
headers (`Access-Control-Allow-Origin`, `Access-Control-Allow-Headers`,
`Access-Control-Allow-Methods`) — Lambda proxy integration only passes
headers through for status codes explicitly declared in Method
Response. This bit CORS twice already in this project's history, so
don't skip it. Deploy to a `prod` stage.

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

**Step 9 — Test the customer flow**
Open the frontend's S3 website URL, submit the booking form, then use
the returned `appointment_id` in the request form.

**Step 10 — Test the staff flow**
On the same page, scroll to the Staff Portal: Register a staff
account, log in, then check the Dashboard tab shows the appointment
you just created.

**Step 11 — Verify the event pipeline**
- `Appointments` and `Bays` tables updated
- `work-orders/<appointment_id>.txt` present in the docs bucket
- CloudWatch Logs for `NotificationFunction` show a `[NOTIFY] ...` line
- `Notifications` table has a new item
- `Employees` table has your new staff account (with a `password_hash`,
  never a plaintext password)
- `Sessions` table has a token entry after login

## 5. Project structure

```
fleet-cloud-project/
├── frontend/index.html              (customer booking + staff portal)
├── lambda/
│   ├── appointment_handler.py
│   ├── service_request_handler.py
│   ├── notification_handler.py
│   ├── auth_register_handler.py
│   ├── auth_login_handler.py
│   ├── auth_utils.py                (password hashing, shared)
│   ├── dashboard_handler.py
│   ├── session_utils.py             (session validation, shared)
│   └── vehicle_service_engine/      (vendored copy of lib/)
├── lib/vehicle_service_engine/      (source of truth for the library)
│   ├── __init__.py
│   ├── cancellation_policy.py
│   ├── labor_pricing.py
│   └── bay_allocation_resolver.py
└── tests/
    ├── test_vehicle_service_engine.py
    └── test_auth_utils.py
```

## 6. Tearing down (only after grading)
Delete the Lambda functions, API Gateway, DynamoDB tables, SNS topic,
SQS queues, and S3 buckets via the console or `aws` CLI.
