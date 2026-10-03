# UPI Guard — Product Expansion & Claude Implementation Specification

> **Purpose:** This document is a handoff specification for Claude Code / Claude Pro.
>
> **Repository:** `https://github.com/PrathmeshPawar2110/UPI_Fraud_Detection`
>
> **Important:** Extend the existing application. Do **not** rewrite the current fraud-detection engine unless required. Preserve working behavior and add features incrementally.

---

# 1. Product Vision

Transform the current **UPI Fraud Check** application from a single-transaction fraud checker into a complete:

# **UPI Guard — Personal UPI Fraud Detection, Investigation & Prevention Platform**

The product should help a user:

1. Scan a UPI/payment screenshot.
2. Detect potentially fraudulent transactions.
3. Understand **why** a transaction was flagged.
4. Import multiple transactions.
5. Maintain a personal transaction history.
6. Detect suspicious patterns across transactions.
7. Investigate suspicious UPI IDs/accounts.
8. Scan suspicious SMS/messages.
9. Analyze suspicious payment URLs.
10. Detect QR/payment-link risks.
11. Report suspicious entities.
12. Simulate fraud scenarios.
13. Generate a fraud incident report.
14. Get guided next steps after suspected fraud.
15. Ask an AI investigator questions about their transaction evidence.
16. See relationships between accounts/UPI IDs/transactions.
17. Receive simulated real-time fraud alerts.
18. Manage privacy/consent settings.
19. Learn about common UPI scams through an interactive experience.

The result should feel like a **real consumer cybersecurity/FinTech product**, not a college CRUD application or an admin dashboard.

---

# 2. Existing System — DO NOT BREAK THIS

The current application already contains:

- React frontend
- Vite
- FastAPI backend
- Tesseract.js browser-side OCR
- UPI screenshot parsing
- Google Pay / PhonePe / Paytm / BHIM-style receipt parsing
- Sent-payment fraud detection
- LightGBM-trained model
- Exported tree inference
- TreeSHAP explanations
- Received-money rule engine
- Risk level
- Fraud probability
- Plain-English reasons
- Next-step guidance
- Tests
- GitHub Actions CI/CD
- Vercel deployment

Current flow:

```text
Screenshot
    ↓
Tesseract.js OCR
    ↓
ocrParse.js
    ↓
Transaction Form
    ↓
FastAPI
    ↓
Fraud Model / Rules
    ↓
Risk + Reasons
    ↓
Result
```

### Preserve these principles

- OCR remains browser-side.
- Do not send raw screenshots to the backend unless explicitly required.
- Do not expose model internals unnecessarily.
- Keep existing API behavior backward compatible.
- Keep existing tests passing.
- Do not remove the current sent-money model.
- Do not replace SHAP with a generic LLM explanation.
- The AI layer must explain evidence already produced by deterministic/model components rather than inventing fraud reasons.

---

# 3. New Product Architecture

Target architecture:

```text
                         UPI GUARD
                            │
       ┌────────────────────┼────────────────────┐
       │                    │                    │
   INPUT LAYER          INTELLIGENCE        USER ACTIONS
       │                    │                    │
       ↓                    ↓                    ↓
 Screenshot OCR        ML Fraud Model       Investigation
 CSV Import            Rule Engine          Report
 Statement Import      Pattern Engine       Alerts
 Message Scanner       Risk Engine          Scam Report
 URL Scanner           Graph Engine         Emergency Help
 QR Scanner            AI Investigator      Simulator
       │                    │
       └───────────┬────────┘
                   ↓
           Transaction Store
                   │
           PostgreSQL / SQLite
                   │
        ┌──────────┼──────────┐
        ↓          ↓          ↓
     Users      Transactions  Reports
                   │
                   ↓
             Risk History
```

For the educational/local version, SQLite is acceptable.

For the more complete version, prefer PostgreSQL.

---

# 4. Core Website Information Architecture

This is a website/application, NOT a dashboard-only product.

## Public Pages

### `/`

Landing page.

Hero:

> **Protect every UPI payment.**

Subheading:

> Detect suspicious transactions, understand fraud signals, investigate UPI activity and know what to do next.

Primary CTA:

> **Check a Payment**

Secondary CTA:

> **Explore Fraud Protection**

Sections:

- How it works
- Supported scan types
- Fraud scenarios
- Why explanations matter
- Privacy/security
- Emergency assistance
- Demo mode

---

### `/check`

Main transaction checker.

Modes:

1. Upload screenshot
2. Paste/type transaction details
3. Upload statement
4. Scan QR
5. Check UPI ID
6. Check payment URL

---

### `/transactions`

Personal transaction history.

Features:

- Search
- Filters
- Date range
- Risk level
- Amount range
- Merchant
- UPI ID
- Payment app
- Sent/received
- Fraud status

Transaction cards should show:

```text
₹82,000
abc@ybl
Oct 03, 2026 · 12:48 AM

HIGH RISK

[ Investigate ]
```

---

### `/investigate/:transactionId`

Detailed fraud investigation.

Show:

- Transaction information
- Risk score
- Risk level
- Model reasons
- Rule reasons
- SHAP contribution summary
- Transaction timeline
- Related transactions
- Related UPI IDs
- Device/location information if available in demo data
- Recommended next actions
- Add investigation note
- Mark as reviewed
- Report fraud
- Generate report

---

### `/network`

Fraud relationship graph.

Nodes:

- User
- UPI ID
- Transaction
- Account
- Merchant
- Device
- Location

Edges:

- SENT
- RECEIVED
- USED_BY
- CONNECTED_TO
- SAME_DEVICE
- SAME_UPI
- SAME_LOCATION

Allow:

- zoom
- pan
- click node
- filter by risk
- highlight suspicious paths

---

### `/message-scanner`

Suspicious SMS/message scanner.

Input:

- pasted message
- screenshot
- OCR result

Extract:

- bank name
- UPI ID
- URL
- phone number
- amount
- urgency indicators
- credential/OTP requests

Output:

```text
HIGH RISK

Possible scam:
KYC / phishing

Indicators:
- urgent account threat
- suspicious link
- impersonation
- request for sensitive action
```

---

### `/url-checker`

Suspicious payment URL checker.

Analyze:

- URL structure
- HTTPS
- domain
- suspicious keywords
- redirect patterns where technically available
- domain/brand mismatch
- URL shorteners
- known-safe/unsafe demo lists

Do NOT claim a URL is malicious solely because of one weak heuristic.

Return:

- SAFE
- SUSPICIOUS
- HIGH RISK
- UNKNOWN

Always explain the basis.

---

### `/upi-check`

UPI ID investigation.

Input:

```text
example@ybl
```

Show:

- Format validation
- PSP/provider
- User reports
- Number of local transactions
- Total received/sent
- Risk signals
- Related transactions
- Report entity

For the demo, community reports and history can come from the application's own database.

Do not claim the data is an official NPCI/bank blacklist.

---

### `/qr-scanner`

QR security checker.

Support:

- Upload QR image
- Camera scan if feasible
- Decode UPI URI
- Extract:
  - payee
  - VPA
  - amount
  - currency
  - merchant
  - URL if present

Then analyze:

```text
QR PAYMENT

Payee: abc@ybl
Amount: ₹5,000

Risk: MEDIUM

Warnings:
- Unknown recipient
- Amount pre-filled
- Recipient has no local history
```

---

### `/reports`

User's submitted fraud reports.

Allow:

- create report
- view report
- update report status
- attach evidence metadata
- export report

---

### `/simulator`

Fraud simulation lab.

Scenarios:

1. Account takeover
2. Fake refund
3. KYC scam
4. Wrong-transfer scam
5. Fake customer support
6. Investment scam
7. QR scam
8. Phishing
9. Payment screenshot fraud

Simulation should generate a timeline and feed events into the same risk engine.

---

### `/alerts`

Fraud alerts.

Show:

- newly detected high-risk transactions
- suspicious patterns
- repeated transfers
- sudden amount spike
- new recipient
- unusual transaction time
- rapid transaction burst

For local/demo mode, use simulated real-time transactions.

---

### `/subscriptions`

Optional financial intelligence feature.

Detect recurring merchant patterns.

Example:

```text
Netflix       ₹649/month
Spotify       ₹119/month
YouTube       ₹129/month
```

This is not the primary fraud feature, but it demonstrates how the platform can become a broader personal financial-security layer.

---

### `/emergency`

Emergency fraud-response workflow.

When a transaction is high risk:

```text
POSSIBLE FRAUD

1. Stop further payments
2. Preserve transaction details
3. Contact your bank
4. Report suspected cyber fraud
5. Secure compromised accounts
```

Include links to official resources where appropriate.

Do not pretend the application can directly freeze a bank account unless a real authorized integration exists.

---

### `/learn`

Interactive fraud education.

Cards:

- UPI scams
- Fake payment screenshots
- KYC scams
- OTP scams
- QR scams
- Remote-access scams
- Investment scams
- Wrong-transfer scams
- Fake customer care
- Social engineering

Use mini quizzes.

---

### `/settings`

Include:

- Privacy
- Data retention
- Delete transaction history
- Export data
- Notification settings
- Demo mode
- Connected integrations
- Consent settings

---

# 5. Transaction Data Model

Create a normalized transaction model.

Suggested schema:

```text
Transaction
-----------
id
external_id
timestamp
direction
amount
currency
sender_name
sender_upi
receiver_name
receiver_upi
payment_app
bank
transaction_type
status
balance_before
balance_after
location
device_id
ip_hash
merchant
category
fraud_score
risk_level
risk_source
is_fraud_confirmed
is_reviewed
created_at
updated_at
```

Do not store sensitive raw credentials.

Never store:

- UPI PIN
- bank password
- OTP
- CVV
- debit-card PIN
- authentication secrets

---

# 6. Fraud Event Model

Create an event model for sequences.

```text
FraudEvent
----------
id
transaction_id
event_type
timestamp
source
severity
metadata
```

Examples:

```text
NEW_DEVICE
NEW_RECIPIENT
LARGE_AMOUNT
RAPID_TRANSFER
UNUSUAL_HOUR
BALANCE_DEPLETION
MULTIPLE_FAILED_ATTEMPTS
SUSPICIOUS_UPI
SUSPICIOUS_URL
```

This will enable sequence detection later.

---

# 7. Fraud Risk Engine

Create a unified risk engine.

Inputs:

```text
ML Score
+
Rule Score
+
Pattern Score
+
Network Score
+
Reputation Score
```

Do NOT simply average everything blindly.

Create a documented scoring strategy.

Example:

```text
ML probability:        0.72
Rule risk:             0.80
Pattern risk:          0.65
Network risk:          0.90

Final risk:            0.77
Risk level:            HIGH
```

Keep the individual components visible for explainability.

---

# 8. Advanced Pattern Detection

Add deterministic pattern detectors.

## Pattern 1 — Rapid transfers

Example:

```text
₹50,000
₹45,000
₹30,000
```

within 5 minutes.

Flag:

> Rapid transaction burst.

---

## Pattern 2 — Balance drain

If:

```text
Balance before: ₹100,000
Transaction: ₹92,000
```

flag:

> Possible balance depletion.

---

## Pattern 3 — New recipient

If recipient has not appeared in historical transactions:

> New recipient detected.

---

## Pattern 4 — Unusual amount

Compare against the user's historical amount distribution.

Example:

```text
Normal:
₹500–₹4,000

Current:
₹82,000
```

---

## Pattern 5 — Unusual hour

Compare against historical transaction times.

---

## Pattern 6 — Transaction burst

Detect unusually high transaction count within a short time window.

---

## Pattern 7 — Recipient concentration

Detect repeated payments to a newly introduced recipient.

---

## Pattern 8 — Circular money movement

Detect:

```text
A → B → C → A
```

for demo/synthetic data.

---

# 9. Fraud Network Graph

Build graph relationships from stored transactions.

Example:

```text
User
 |
 +---- Transaction ----> UPI ID
                           |
                           +---- Account
                           |
                           +---- Merchant
```

Add suspicious-cluster detection.

Possible future algorithms:

- connected components
- degree anomaly
- shared-recipient detection
- suspicious fan-in
- suspicious fan-out
- circular paths

Keep graph analysis separate from the existing transaction classifier.

---

# 10. AI Fraud Investigator

Add an AI assistant only after the deterministic system works.

The assistant should answer questions using structured application data.

Example questions:

> Why was this transaction flagged?

> What happened before this transaction?

> Show all transactions related to this UPI ID.

> Which transactions are highest risk?

> Is this pattern consistent with account takeover?

> Summarize this fraud case.

> Create an investigation report.

The AI must cite the internal evidence it used:

```text
Evidence:
- Transaction amount: ₹82,000
- Historical median: ₹2,400
- New recipient: Yes
- Transaction time: 00:48
- Related transactions in previous 5 minutes: 2
```

Never allow the LLM to invent transaction facts.

---

# 11. AI Features That Are Safe and Useful

Potential AI functions:

### Explain

Turn model/rule evidence into plain English.

### Summarize

Create a case summary.

### Investigate

Retrieve related transactions.

### Search

Natural-language transaction search.

Example:

> "Find transactions above ₹50,000 involving new recipients."

### Report generation

Create a structured incident report.

### Education

Explain why a scam technique is dangerous.

---

# 12. Community Fraud Intelligence

Create a local reporting database.

Users can report:

- UPI ID
- phone number
- URL
- scam category
- amount
- date
- description

Store only appropriate, non-sensitive information.

Add moderation/status:

```text
PENDING
REVIEWED
CONFIRMED_BY_USER
DISPUTED
REMOVED
```

Never automatically label a real person as a criminal based only on an unverified user report.

---

# 13. Fraud Simulator

Create a scenario engine.

Example:

```text
Scenario:
Account Takeover

12:01 Login from new device
12:03 New beneficiary
12:04 ₹50,000 transfer
12:05 ₹40,000 transfer
12:06 ₹30,000 transfer
```

Feed these events through the same fraud engine.

Then show:

```text
Detected:
✓ New device
✓ New recipient
✓ Rapid transfers
✓ Large amount
✓ Balance depletion

Risk: HIGH
```

This becomes the primary live demo feature.

---

# 14. Real-Time Demo Mode

Create a demo mode that emits synthetic transactions every few seconds.

Example:

```text
Transaction stream
       ↓
Risk Engine
       ↓
LOW / MEDIUM / HIGH
       ↓
Alert
```

Use WebSockets or Server-Sent Events if appropriate.

Do not connect to real banking systems for the demo.

---

# 15. Fraud Case Management

Introduce:

```text
Case
----
id
title
status
priority
created_at
assigned_to
transactions
evidence
notes
resolution
```

Statuses:

```text
OPEN
INVESTIGATING
ESCALATED
RESOLVED
FALSE_POSITIVE
```

This makes the application resemble a real fraud investigation system.

---

# 16. Evidence Vault

Allow a case to reference:

- screenshot metadata
- transaction
- message
- URL
- QR payload
- notes
- timestamps

Do not store raw sensitive information unnecessarily.

Use local/demo storage for the college project.

---

# 17. Incident Report

Generate a downloadable report.

Report sections:

```text
UPI FRAUD INCIDENT REPORT

Case ID

Transaction Summary

Risk Assessment

Model Evidence

Rule Evidence

Timeline

Related Entities

Investigation Notes

Recommended Next Steps
```

Make PDF generation optional.

---

# 18. Notifications

Support:

- in-app alerts
- browser notifications where supported
- email as optional future integration

Examples:

```text
🚨 High-risk transaction detected

₹82,000 → abc@ybl

[Investigate]
```

Do not send actual bank alerts or claim to be an official bank notification.

---

# 19. Privacy & Security

This is a financial-security product, so security is part of the project.

Implement:

- no bank passwords
- no UPI PINs
- no OTP storage
- input validation
- rate limiting
- CORS restrictions
- secure headers
- request size limits
- file type validation
- image size limits
- URL validation
- database access controls
- audit logs
- data deletion
- export data
- clear demo/synthetic-data labeling

Add a visible:

> **Privacy First**

section.

---

# 20. Account Aggregator / Bank Integration — FUTURE ARCHITECTURE ONLY

Do NOT implement fake bank APIs.

For a real-world future architecture, investigate consent-based financial-data systems such as India's Account Aggregator ecosystem.

For the college project:

```text
Mock Bank
   ↓
Mock Consent
   ↓
Mock Financial Data Provider
   ↓
UPI Guard
```

The UI should make it clear this is a simulation.

Do not ask users for bank usernames/passwords.

---

# 21. UX / Visual Direction

The application should feel like:

- modern FinTech
- cybersecurity product
- consumer application
- premium
- trustworthy
- minimal
- interactive

Avoid:

- generic Bootstrap dashboard
- excessive cards
- huge tables
- too many charts
- "AI generated" looking UI
- unnecessary gradients
- fake statistics

Use the existing typography system unless a deliberate redesign is justified.

Potential visual language:

```text
Dark / light neutral base
Strong warning colors only for risk
Large typography
Subtle motion
Clean evidence panels
Interactive transaction timeline
Network graph
Scanner experiences
```

Risk colors:

```text
LOW       → calm
MEDIUM    → warning
HIGH      → danger
UNKNOWN   → neutral
```

Do not rely on color alone; always include text/icons.

---

# 22. Suggested Frontend Structure

Refactor toward:

```text
src/
├── app/
│   ├── routes/
│   └── providers/
│
├── components/
│   ├── transaction/
│   ├── fraud/
│   ├── scanner/
│   ├── graph/
│   ├── alerts/
│   ├── reports/
│   └── common/
│
├── pages/
│   ├── Home/
│   ├── Check/
│   ├── Transactions/
│   ├── Investigation/
│   ├── Network/
│   ├── MessageScanner/
│   ├── URLChecker/
│   ├── QRScanner/
│   ├── Reports/
│   ├── Simulator/
│   ├── Alerts/
│   ├── Learn/
│   └── Settings/
│
├── services/
│   ├── api/
│   ├── transactions/
│   └── fraud/
│
├── hooks/
├── utils/
├── types/
└── styles/
```

Do not blindly follow this structure if the existing project has a better established pattern.

---

# 23. Suggested Backend Structure

Move toward:

```text
backend/
├── main.py
├── api/
│   ├── predict.py
│   ├── transactions.py
│   ├── investigation.py
│   ├── reports.py
│   ├── messages.py
│   ├── urls.py
│   ├── qr.py
│   ├── network.py
│   ├── alerts.py
│   └── simulator.py
│
├── fraud/
│   ├── model.py
│   ├── rules.py
│   ├── patterns.py
│   ├── risk_engine.py
│   ├── predictor.py
│   └── explain.py
│
├── services/
│   ├── transaction_service.py
│   ├── investigation_service.py
│   ├── report_service.py
│   └── notification_service.py
│
├── models/
├── schemas/
├── db/
└── tests/
```

Preserve existing files when possible.

---

# 24. API Expansion

Existing APIs must remain compatible.

Add endpoints approximately like:

```text
POST /api/predict
POST /api/check-received
GET  /api/model-info

POST /api/transactions/import
GET  /api/transactions
GET  /api/transactions/{id}

GET  /api/investigations/{id}
POST /api/investigations/{id}/notes

POST /api/message/analyze
POST /api/url/analyze
POST /api/qr/analyze

GET  /api/upi/{vpa}
POST /api/reports

GET  /api/network/{entity}
GET  /api/network/transaction/{id}

GET  /api/alerts
POST /api/alerts/{id}/read

POST /api/simulator/start
POST /api/simulator/events

POST /api/reports/{case_id}/generate
```

Use Pydantic schemas for every request/response.

---

# 25. Database

Recommended tables:

```text
users
transactions
fraud_events
risk_scores
investigations
investigation_notes
fraud_reports
reported_entities
message_scans
url_scans
qr_scans
alerts
simulation_sessions
simulation_events
audit_logs
```

For local development:

- SQLite is acceptable.

For scalable deployment:

- PostgreSQL.

---

# 26. Testing Requirements

Every new feature must have tests.

Backend:

- unit tests
- API tests
- validation tests
- fraud-rule tests
- pattern tests
- risk-engine tests

Frontend:

- OCR parser tests
- component tests where useful
- API error states
- loading states
- empty states

Security:

- invalid file types
- oversized uploads
- malformed URLs
- malformed UPI IDs
- injection attempts
- invalid transaction amounts
- unauthorized record access

Most important:

> Existing tests must remain green after every phase.

---

# 27. Demo Dataset

Create a clearly synthetic dataset containing:

### Legitimate

- normal small transactions
- recurring bills
- normal merchants

### Fraud patterns

- large transfer
- new recipient
- rapid transfers
- balance drain
- unusual time
- suspicious UPI
- QR scam
- fake refund
- account takeover

Label it clearly:

> SYNTHETIC DEMO DATA — NOT REAL BANK DATA

---

# 28. Demo Journey for Presentation

The ideal 5-minute demo:

### Step 1

Open landing page.

### Step 2

Upload a fake UPI screenshot.

### Step 3

OCR extracts transaction details.

### Step 4

Fraud engine returns:

```text
HIGH RISK — 91
```

### Step 5

Click:

> Investigate

### Step 6

Show:

- reasons
- SHAP evidence
- transaction timeline
- related transactions

### Step 7

Open network graph.

### Step 8

Show connected suspicious UPI ID.

### Step 9

Run Fraud Simulator.

### Step 10

Show AI Investigator:

> "Why is this suspicious?"

### Step 11

Generate incident report.

### Step 12

Show emergency response instructions.

This gives the evaluator a complete story.

---

# 29. Advanced Ideas — Optional Phase 4

Only implement these after the core product is stable.

## A. Behavioral Baseline

Learn the user's normal transaction behavior:

- average amount
- normal transaction hours
- normal recipients
- normal frequency
- normal merchant patterns

Then detect deviations.

---

## B. Adaptive Risk

Risk should evolve based on history.

Example:

```text
First transaction with recipient:
MEDIUM

Repeated legitimate transactions:
Risk decreases

Sudden large transaction:
Risk increases
```

Do not let historical behavior permanently suppress serious risk signals.

---

## C. Graph-based Fraud Detection

Use graph algorithms to find:

- fan-in
- fan-out
- suspicious clusters
- circular movement
- shared recipients

---

## D. Multilingual Scam Detection

Support:

- English
- Hindi
- Marathi
- Hinglish

Examples:

```text
"OTP bhejo"
"Account band ho jayega"
"KYC update karo"
```

Classify scam intent.

---

## E. Voice Scam Analysis

Optional future feature:

Upload a recorded scam-call transcript/audio if technically/legal constraints allow.

Analyze transcript for:

- urgency
- impersonation
- OTP requests
- remote-access requests
- payment pressure

Keep this as a future feature unless there is a clear implementation path.

---

## F. Privacy-Preserving ML

Advanced research feature:

Explore federated learning or privacy-preserving learning where multiple institutions can improve a fraud model without directly sharing raw transaction records.

This should be a research/demo feature, not a fake production claim.

---

## G. Model Monitoring

Create a developer/admin-only page showing:

- model version
- precision
- recall
- F1
- false positives
- false negatives
- threshold
- feature drift
- prediction distribution

This page is for the project team, not the main consumer UX.

---

# 30. Important Product Safety Rules

The website must never:

1. Claim a person is definitely a criminal.
2. Claim a transaction is definitely fraudulent unless the user has confirmed it.
3. Present synthetic data as real data.
4. Claim to be an official NPCI/bank service.
5. Ask for a UPI PIN.
6. Ask for an OTP.
7. Ask for a bank password.
8. Claim to freeze an account without a real authorized integration.
9. Expose private information from community reports.
10. Invent fraud reasons.

Use wording such as:

> "Potentially suspicious"

> "High-risk pattern detected"

> "The model identified these signals"

rather than:

> "This person is a fraudster."

---

# 31. Development Strategy

Do not implement everything in one huge change.

Use phases.

## Phase 0 — Audit

Claude must first:

- inspect the entire repository
- inspect TRD.md
- inspect README
- inspect frontend
- inspect backend
- inspect tests
- inspect model files
- inspect deployment
- identify existing routes
- identify existing API contracts

Then produce:

```text
CURRENT STATE
ARCHITECTURE
RISKS
REFACTOR PLAN
FILES TO CHANGE
FILES NOT TO CHANGE
```

Do not code until this audit is complete.

---

# 32. Phase 1 — Persistent Transactions

Implement:

- database
- transaction model
- import API
- transaction history
- search/filter
- transaction detail

Keep OCR + prediction working.

---

# 33. Phase 2 — Investigation

Implement:

- investigation page
- risk evidence
- SHAP evidence
- timeline
- related transactions
- notes
- case state

---

# 34. Phase 3 — Pattern Engine

Implement:

- rapid transfer
- unusual amount
- new recipient
- balance drain
- unusual hour
- transaction burst
- recipient concentration

---

# 35. Phase 4 — Network Graph

Implement:

- graph data API
- interactive graph
- suspicious cluster
- entity investigation

---

# 36. Phase 5 — Scam Intelligence

Implement:

- message scanner
- URL scanner
- QR scanner
- UPI ID checker

---

# 37. Phase 6 — Reports & Response

Implement:

- fraud report
- PDF/export
- evidence
- emergency workflow
- report history

---

# 38. Phase 7 — Fraud Simulator

Implement:

- scenario definitions
- synthetic event generation
- real-time stream
- model/rule evaluation
- timeline visualization

---

# 39. Phase 8 — AI Investigator

Only after all structured APIs are stable.

Implement an AI layer that can:

- retrieve transaction data
- retrieve risk evidence
- retrieve case notes
- explain model output
- summarize cases
- answer natural-language queries
- generate reports

The AI must use structured tools/functions rather than directly querying arbitrary database content.

---

# 40. Phase 9 — UI/UX Polish

After functionality is stable:

- responsive mobile layout
- loading states
- skeletons
- empty states
- error states
- animations
- accessibility
- keyboard navigation
- visual hierarchy
- micro-interactions

Do not sacrifice usability for visual effects.

---

# 41. Phase 10 — Production Hardening

Implement:

- authentication
- authorization
- rate limiting
- secure CORS
- security headers
- structured logging
- audit logging
- error tracking
- database migrations
- environment configuration
- secrets management
- deployment verification

---

# 42. Claude Code Working Instructions

Claude should work as an engineering agent, not just produce suggestions.

For every phase:

1. Inspect relevant existing files.
2. Explain the implementation plan.
3. Make small changes.
4. Run tests.
5. Run frontend build.
6. Run backend tests.
7. Fix failures.
8. Inspect the final diff.
9. Update documentation.
10. Report:
   - files changed
   - features added
   - tests run
   - remaining issues

Never silently replace existing working functionality.

---

# 43. Git Strategy

Before major work:

```bash
git status
git checkout -b feature/platform-expansion
```

Create logical commits:

```text
feat: add persistent transaction storage
feat: add investigation workflow
feat: add fraud pattern engine
feat: add fraud network graph
feat: add scam message scanner
feat: add URL risk analyzer
feat: add QR security scanner
feat: add fraud simulator
feat: add AI investigator
feat: add incident reports
```

Avoid one enormous commit.

---

# 44. Claude Skills / Agentic Opportunities

Claude can be used for more than generating individual code snippets.

Use Claude Code to:

### Repository archaeology

Ask it to map:

```text
Frontend → API → model → deployment
```

### Refactoring

Ask it to identify duplicated logic and improve architecture without changing behavior.

### Testing

Ask it to generate missing tests from actual implementation.

### UI implementation

Give it screenshots/reference designs and ask it to implement the UI while preserving functionality.

### Debugging

Give Claude the failing test/build and ask it to reproduce, diagnose, fix and verify.

### Documentation

Ask it to keep:

- README
- TRD
- API docs
- architecture diagrams
- setup instructions

synchronized with code.

### Long-running feature implementation

Give Claude one phase at a time and require it to run tests before moving forward.

### Code review

After implementation:

> Review this feature as a senior security-focused engineer. Find correctness, privacy, security, UX and maintainability problems. Do not modify code yet; report issues first.

Then give a second prompt to fix the approved issues.

---

# 45. Extra Ideas Claude Can Explore

Claude should evaluate feasibility of these, but NOT implement them automatically:

### 1. Natural-language transaction search

User:

> "Show payments above ₹10,000 to new recipients last month."

### 2. Fraud story generation

Turn transaction events into a chronological story.

### 3. Explainable risk comparison

Show:

```text
Why risk increased:
+32 new recipient
+21 unusual amount
+18 unusual hour
+12 rapid transfer
```

### 4. Personal fraud profile

Show the user's normal transaction behavior and deviations.

### 5. Scam knowledge graph

Connect:

```text
Scam type
 ↓
Indicators
 ↓
UPI ID
 ↓
URL
 ↓
Transaction
 ↓
Case
```

### 6. Case similarity

Find previous cases with similar patterns.

### 7. What-if simulator

Ask:

> What if I send ₹80,000 to this new UPI ID?

Run the risk engine without actually executing a payment.

### 8. Explainability playground

Allow the user to toggle signals and see how the risk score changes.

### 9. Fraud training mode

Give the user transactions and ask:

> Fraud or legitimate?

Then explain the answer.

### 10. Synthetic fraud-data generator

Generate controlled synthetic transaction sequences for testing.

---

# 46. Definition of Done

The project is considered successfully expanded when:

- Existing OCR works.
- Existing sent-money model works.
- Existing received-money rules work.
- Existing tests pass.
- Users can store/import transactions.
- Users can investigate transactions.
- Fraud patterns are detected.
- Related transactions can be explored.
- Network relationships can be visualized.
- Messages can be analyzed.
- URLs can be analyzed.
- QR codes can be analyzed.
- UPI IDs can be investigated.
- Fraud cases can be created.
- Reports can be generated.
- Fraud scenarios can be simulated.
- Alerts work in demo mode.
- AI can explain evidence using actual application data.
- No sensitive banking credentials are requested.
- Synthetic/demo data is clearly labeled.
- The UI feels like a consumer cybersecurity/FinTech product.
- The application remains deployable.
- Documentation matches the actual implementation.

---

# 47. First Prompt to Claude

Use this exact starting instruction:

> You are taking over an existing UPI fraud detection project.
>
> Read `docs/TRD.md`, `README.md`, the complete frontend, backend, tests, model implementation and deployment configuration before changing anything.
>
> Do NOT start coding immediately.
>
> First produce a repository audit:
>
> 1. Current architecture
> 2. Existing features
> 3. Existing API contracts
> 4. Existing frontend routes/components
> 5. Existing ML/OCR implementation
> 6. Existing tests
> 7. Existing deployment
> 8. Technical debt
> 9. What must remain backward compatible
> 10. Recommended implementation sequence for this specification
>
> Then wait for approval before implementing Phase 1.
>
> The goal is to evolve the application into **UPI Guard — a personal UPI fraud detection, investigation and prevention platform**.
>
> Do not replace the existing LightGBM/TreeSHAP/OCR implementation. Extend it.
>
> Use `UPI_GUARD_EXPANSION.md` as the product and technical specification.
>
> Every phase must be implemented incrementally, tested, documented and verified before moving to the next phase.

---

# 48. Final Product Positioning

Do not present this as:

> "A machine learning model that predicts UPI fraud."

Present it as:

# **UPI Guard**
### **An AI-assisted UPI fraud detection, investigation and prevention platform.**

The core pipeline:

```text
CHECK
  ↓
DETECT
  ↓
EXPLAIN
  ↓
INVESTIGATE
  ↓
CONNECT
  ↓
ALERT
  ↓
REPORT
  ↓
PREVENT
```

This is the product direction.

---

# 49. Non-Goals

Do NOT implement without explicit approval:

- Real bank credential collection
- Real UPI payment execution
- Real account freezing
- Real NPCI privileged integration
- Real bank transaction scraping
- Fake official-bank functionality
- Storing OTP/PIN/passwords
- Public accusations against individuals
- Presenting synthetic fraud statistics as real statistics

---

# 50. Success Criteria

The final demo should allow an evaluator to say:

> "This isn't just a fraud ML model. It is a complete financial-security product."

A successful end-to-end demo should go:

```text
Screenshot
    ↓
OCR
    ↓
Fraud Detection
    ↓
Explainability
    ↓
Transaction History
    ↓
Pattern Detection
    ↓
Fraud Investigation
    ↓
Network Relationships
    ↓
AI Investigator
    ↓
Incident Report
    ↓
Prevention / Next Steps
```

That is the target.