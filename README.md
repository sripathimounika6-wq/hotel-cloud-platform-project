# Smart Hotel Booking & Room Automation Platform
Hospitality sector — Cloud Platform Programming project (AWS)

## 1. What this is

A serverless hotel booking backend. Guests book rooms (with dynamic,
occupancy-based pricing) and submit housekeeping requests. Bookings
automatically trigger a check-in document generation and guest
notification via an event-driven pipeline.

## 2. Architecture

```
Guest (Cognito-authenticated)
      │
      ▼
API Gateway  ──POST /bookings──▶ BookingFunction (Lambda)
      │                                │
      │                                ├─▶ DynamoDB (BookingsTable, RoomsTable)
      │                                ├─▶ S3 (check-in doc)
      │                                └─▶ SNS "BookingCreated" topic
      │                                          │
      │                                          ▼
      │                                   SQS NotificationQueue
      │                                          │
      │                                          ▼
      │                                 NotificationFunction (Lambda)
      │                                          │
      │                                          ▼
      │                                 DynamoDB (NotificationsTable)
      │
      └──POST /requests──▶ HousekeepingFunction (Lambda)
                                  │
                                  ├─▶ DynamoDB (RequestsTable)
                                  └─▶ SQS HousekeepingQueue (staff tooling polls this)
```

**Pattern used:** event-driven / fan-out via pub-sub (SNS → SQS), decoupling
booking creation from downstream notification processing. This means the
NotificationFunction can fail/retry independently of the booking API call
succeeding — the guest's booking isn't blocked on notification delivery.

**Cloud services used programmatically (6, exceeds the 5 required):**
1. API Gateway — REST trigger for both guest-facing Lambdas
2. Lambda — all three functions
3. DynamoDB — 4 tables (bookings, rooms, requests, notifications)
4. S3 — check-in document storage (object storage requirement)
5. SNS — BookingCreated event topic (pub/sub requirement)
6. SQS — notification queue + housekeeping queue (pub/sub requirement)
7. Cognito — guest authentication (bonus, not counted toward the 5)

## 3. Custom library: `booking_rules_engine`

Located in `lib/booking_rules_engine/`. Pure Python, no AWS dependency,
fully unit tested (`tests/test_booking_rules_engine.py`).

| Module | Purpose |
|---|---|
| `cancellation_policy.py` | Strategy pattern: FLEXIBLE / MODERATE / STRICT refund rules |
| `pricing_strategy.py` | Strategy pattern: occupancy-based + last-minute dynamic pricing |
| `overbooking_resolver.py` | Prioritises which bookings keep their room when oversold |

`booking_handler.py` imports `PricingEngine` to compute nightly rates —
this is the "meaningful functionality" the library provides to the app.

Run tests locally:
```bash
cd hotel-cloud-project
python -m pytest tests/ -v
```

## 4. How this was actually deployed

Two deployment paths are documented here:

**A. Infrastructure-as-code (infra/template.yaml)** — an AWS SAM template
that defines every resource declaratively. This is the reference
architecture and is what `sam deploy` would provision if built in an
environment with a matching local Python version and Docker available.

**B. Manual AWS Console deployment (what was actually run for this
submission)** — because the AWS Academy Learner Lab account restricts
IAM role creation and the local machine's Python version didn't match
the Lambda runtime for a container-free SAM build, the application was
deployed by creating each resource directly in the AWS Console:

1. **S3 buckets** — one for guest check-in documents (private), one for
   hosting the static frontend (public read, static website hosting enabled)
2. **DynamoDB tables** — `Bookings`, `Rooms`, `Requests`, `Notifications`
   (created via console, on-demand billing mode)
3. **SNS topic** — `BookingCreatedTopic`
4. **SQS queues** — `NotificationQueue` (subscribed to the SNS topic),
   `HousekeepingQueue`
5. **Lambda functions** — `BookingFunction`, `HousekeepingFunction`,
   `NotificationFunction`, each uploaded as a `.zip` (handler + vendored
   `booking_rules_engine` library where needed), execution role set to
   the Learner Lab's pre-existing `LabRole`, environment variables set
   per function to point at the resources above
6. **API Gateway** — REST API `HotelApi` with `POST /bookings` and
   `POST /requests` resources, Lambda proxy integration, deployed to a
   `prod` stage
7. **Frontend** — `frontend/index.html` uploaded to the static-hosting
   S3 bucket, bucket policy applied via `aws s3api put-bucket-policy`
   granting public `s3:GetObject`

The `infra/template.yaml` remains in this repo as the documented,
intended infrastructure-as-code design (relevant to the architecture
and CI/CD discussion in the report), even though the actual submitted
deployment was provisioned manually due to the lab environment's
constraints.

## 5. Frontend

`frontend/index.html` is a single-file static site (HTML/CSS/JS, no
build step) with two forms:
- **Reserve a room** → calls `POST {api}/bookings`
- **Request housekeeping** → calls `POST {api}/requests`

It's hardcoded with the deployed API Gateway invoke URL in the "API
endpoint" field at the bottom of the page (editable if the API is
redeployed at a new URL). Hosted on S3 with static website hosting
enabled — this is the public application URL for the examiner.


## 6. Reproducing the deployment (manual AWS Console + CLI path)

**Prerequisites**
- AWS account or AWS Academy Learner Lab access
- AWS CLI installed and configured with valid credentials
- (Optional, for the infra-as-code path) AWS SAM CLI + Docker, if you
  want to deploy `infra/template.yaml` directly instead of following
  the manual steps below

**Step 1 — Create the S3 buckets**
- One private bucket for check-in documents
- One public bucket with static website hosting enabled, for the frontend

**Step 2 — Create the DynamoDB tables**
`Bookings` (PK: `booking_id`), `Rooms` (PK: `room_type`, SK: `date`),
`Requests` (PK: `request_id`), `Notifications` (PK: `notification_id`) —
all on-demand billing.

**Step 3 — Create the SNS topic and SQS queues**
Topic `BookingCreatedTopic`; queues `NotificationQueue` and
`HousekeepingQueue`; subscribe `NotificationQueue` to the topic.

**Step 4 — Create the three Lambda functions**
For each: Python 3.12 runtime, execution role = your account's existing
Lambda role (e.g. `LabRole` in an Academy Lab), upload the handler +
vendored `booking_rules_engine` library (only `BookingFunction` needs
it) as a `.zip`, set the handler to `<file>.handler`, and set the
environment variables listed in `infra/template.yaml` under each
function's block.

**Step 5 — Wire NotificationQueue → NotificationFunction**
Add an SQS trigger on `NotificationFunction` pointing at `NotificationQueue`.

**Step 6 — Create the API Gateway**
REST API with `POST /bookings` → `BookingFunction` and `POST /requests`
→ `HousekeepingFunction`, both with Lambda proxy integration, deployed
to a `prod` stage.

**Step 7 — Upload the frontend**
```bash
aws s3 cp frontend/index.html s3://<your-frontend-bucket>/index.html
aws s3 website s3://<your-frontend-bucket>/ --index-document index.html
aws s3api put-bucket-policy --bucket <your-frontend-bucket> --policy file://bucket-policy.json
```
where `bucket-policy.json` grants public `s3:GetObject` on the bucket.

**Step 8 — Seed a room record**
```bash
aws dynamodb put-item \
  --table-name Rooms \
  --item '{"room_type":{"S":"Deluxe"},"date":{"S":"2026-08-15"},"total_rooms":{"N":"10"},"booked_rooms":{"N":"6"}}'
```

**Step 9 — Test**
Open the frontend's S3 website URL in a browser, fill in the booking
form, and submit — or test directly:
```bash
curl -X POST "<api-invoke-url>/bookings" \
  -H "Content-Type: application/json" \
  -d '{"guest_name":"Jane Doe","room_type":"Deluxe","checkin_date":"2026-08-15","base_rate":150.00,"cancellation_policy":"MODERATE"}'
```

**Step 10 — Verify the event pipeline fired**
- `Bookings` and `Rooms` tables updated
- `checkin-docs/<booking_id>.txt` present in the documents bucket
- CloudWatch Logs for `NotificationFunction` show a `[NOTIFY] ...` line
- `Notifications` table has a new item

## 7. Tearing down (only after grading — do not modify before the deadline)

Delete the Lambda functions, API Gateway, DynamoDB tables, SNS topic,
SQS queues, and S3 buckets via the console or `aws` CLI, or run
`sam delete` if you deployed via the `infra/template.yaml` path instead.

## 8. Project structure

```
hotel-cloud-project/
├── frontend/
│   └── index.html               (static site — booking + housekeeping forms)
├── lambda/
│   ├── booking_handler.py
│   ├── housekeeping_handler.py
│   ├── notification_handler.py
│   ├── booking_rules_engine/   (vendored copy of lib/)
│   └── requirements.txt
├── lib/
│   └── booking_rules_engine/   (source of truth for the library)
│       ├── __init__.py
│       ├── cancellation_policy.py
│       ├── pricing_strategy.py
│       └── overbooking_resolver.py
├── infra/
│   └── template.yaml            (SAM/CloudFormation)
├── tests/
│   └── test_booking_rules_engine.py
└── README.md
```
