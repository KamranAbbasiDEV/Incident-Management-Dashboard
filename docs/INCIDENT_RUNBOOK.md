# Incident response exercise (synthetic data)

This runbook is a training exercise for the demo dashboard. It is not connected to a live monitoring or ticketing system.

## 1. Triage

Record the affected service and reported symptom. Verify supporting telemetry outside the dashboard if this were a real incident. Choose severity based on demonstrable impact rather than a guess.

## 2. Assign and investigate

Create the incident, assign an owner, and transition from **Open** to **Investigating**. Record clear timeline notes: observations, timestamps, suspected dependencies and escalation actions. Avoid customer PII and secrets.

## 3. Mitigate

If a workaround reduces immediate impact, move to **Mitigated**. Explain the workaround and outstanding follow-up in the timeline. A mitigation does not necessarily mean the root cause is understood.

## 4. Resolve

Confirm that the affected service has recovered before choosing **Resolved**. Record what was verified. The dashboard stores a resolution timestamp and includes the incident in its MTTR calculation.

## 5. Reopen if needed

If the issue recurs, move the incident from **Resolved** back to **Investigating**. The old resolved timestamp is cleared and a new resolution time is assigned when resolved again.

## Escalation note template

- Incident ID:
- Service and impact:
- Severity and justification:
- Timeline (UTC):
- Evidence collected:
- Reproduction steps:
- Current owner:
- Mitigation / recovery status:
- Stakeholder update:
- Verified root cause (only if confirmed):
- Follow-up corrective actions:

The dashboard's event history demonstrates operational documentation but is not an immutable audit record.
