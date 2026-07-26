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

## 4. Prerequisites

- AWS account with admin/appropriate IAM permissions
- AWS CLI installed and configured (`aws configure`)
- AWS SAM CLI installed (`pip install aws-sam-cli` or via your OS package manager)
- Python 3.12

## 5. Step-by-step deployment

**Step 1 — Confirm the library is vendored into the Lambda folder**
(already done in this project — `lambda/booking_rules_engine/` is a copy
of `lib/booking_rules_engine/`, since SAM packages each function from a
single `CodeUri` directory.)

```bash
cd hotel-cloud-project
ls lambda/booking_rules_engine   # should show the library files
```

**Step 2 — Validate the template**
```bash
cd infra
sam validate --template template.yaml
```

**Step 3 — Build**
```bash
sam build --template template.yaml
```
This installs `boto3` (already in the Lambda runtime, but pinned for
consistency) and stages each function + the vendored library into
`.aws-sam/build/`.

**Step 4 — Deploy (guided, first time)**
```bash
sam deploy --guided
```
You'll be prompted for:
- Stack name, e.g. `hotel-booking-stack`
- AWS Region, e.g. `eu-west-1`
- Confirm changes before deploy: `Y`
- Allow SAM to create IAM roles: `Y`
- Save arguments to `samconfig.toml`: `Y`

Subsequent deploys just need `sam deploy`.

**Step 5 — Note the outputs**
After deploy, SAM prints:
```
Outputs
-----------------------------------------------------------
Key                 ApiUrl
Value               https://xxxxxxxxxx.execute-api.eu-west-1.amazonaws.com/prod/

Key                 UserPoolId
Value               eu-west-1_xxxxxxxxx

Key                 UserPoolClientId
Value               xxxxxxxxxxxxxxxxxxxxxxxxxx
```
Save these — you'll need the User Pool details to create a test guest
user and get an auth token.

**Step 6 — Create a test guest user in Cognito**
```bash
aws cognito-idp sign-up \
  --client-id <UserPoolClientId> \
  --username guest1@example.com \
  --password TestPass123

aws cognito-idp admin-confirm-sign-up \
  --user-pool-id <UserPoolId> \
  --username guest1@example.com
```

**Step 7 — Get an auth token**
```bash
aws cognito-idp initiate-auth \
  --client-id <UserPoolClientId> \
  --auth-flow USER_PASSWORD_AUTH \
  --auth-parameters USERNAME=guest1@example.com,PASSWORD=TestPass123
```
Copy the `IdToken` from the response.

**Step 8 — Seed a room/occupancy record (so pricing has something to read)**
```bash
aws dynamodb put-item \
  --table-name <RoomsTable-name-from-console> \
  --item '{"room_type":{"S":"Deluxe"},"date":{"S":"2026-08-15"},"total_rooms":{"N":"10"},"booked_rooms":{"N":"6"}}'
```

**Step 9 — Call the API**
```bash
curl -X POST <ApiUrl>bookings \
  -H "Authorization: <IdToken>" \
  -H "Content-Type: application/json" \
  -d '{
    "guest_name": "Jane Doe",
    "room_type": "Deluxe",
    "checkin_date": "2026-08-15",
    "base_rate": 150.00,
    "cancellation_policy": "MODERATE"
  }'
```
Expected: `201` with a JSON booking record including the computed price.

**Step 10 — Verify the event pipeline**
- Check `BookingsTable` and `RoomsTable` in the DynamoDB console — the
  booking should be present and `booked_rooms` incremented
- Check the S3 bucket — a `checkin-docs/<booking_id>.txt` object should exist
- Check CloudWatch Logs for `NotificationFunction` — should show the
  `[NOTIFY] ...` log line, and `NotificationsTable` should have a new item

**Step 11 — Test housekeeping requests**
```bash
curl -X POST <ApiUrl>requests \
  -H "Authorization: <IdToken>" \
  -H "Content-Type: application/json" \
  -d '{"booking_id": "<booking_id from step 9>", "request_type": "TOWELS", "notes": "extra towels please"}'
```

## 6. Tearing down (after grading, if needed)

```bash
sam delete --stack-name hotel-booking-stack
```
(Note: for the actual assessment, keep the app deployed and unmodified
after the submission deadline — don't tear it down until after grading.)

## 7. Project structure

```
hotel-cloud-project/
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
