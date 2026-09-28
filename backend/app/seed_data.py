INCIDENTS = [
    {
        "id": "INC-2026-041", "title": "Checkout timeouts after traffic surge", "timestamp": "2026-08-14T10:32:00Z",
        "service": "checkout-api", "severity": "SEV-2", "symptoms": ["p95 latency rose from 240ms to 8.4s", "checkout requests timing out", "database pool at 100%"],
        "error_signatures": ["TimeoutError: acquiring connection from pool exceeded 5s", "SQLSTATE 53300"], "deployment": "checkout-2.18.3",
        "configuration_context": "Traffic 3x baseline; pool max_size=20; no schema change.",
        "actions": [{"action": "Restart checkout-api pods", "outcome": "failed", "notes": "Timeouts returned within 4 minutes; pool saturation remained."},
                    {"action": "Increase DB pool max_size from 20 to 45 after checking DB headroom", "outcome": "successful", "notes": "Pool wait dropped below 1%; p95 returned to 310ms."}],
        "confirmed_root_cause": "Connection pool capacity was below demand during a sustained traffic increase.", "resolution": "Raised pool size to 45 after verifying database connection headroom.", "resolution_minutes": 27,
    },
    {
        "id": "INC-2026-037", "title": "Checkout timeout with lock contention", "timestamp": "2026-07-29T16:08:00Z",
        "service": "checkout-api", "severity": "SEV-2", "symptoms": ["checkout latency above 6s", "intermittent payment confirmation timeout", "database pool wait elevated"],
        "error_signatures": ["canceling statement due to lock timeout", "SQLSTATE 55P03"], "deployment": "checkout-2.17.9",
        "configuration_context": "Backfill job ran concurrently; pool max_size=40 and utilization was 54%.",
        "actions": [{"action": "Increase connection pool", "outcome": "failed", "notes": "Pool utilization was not saturated; symptom persisted."},
                    {"action": "Pause the noncritical backfill and inspect lock waiters", "outcome": "successful", "notes": "Lock queue cleared; payment confirmation recovered."}],
        "confirmed_root_cause": "A backfill transaction held row locks on the payment order table.", "resolution": "Paused the backfill, allowed the blocked transaction queue to drain, then rescheduled it off peak.", "resolution_minutes": 19,
    },
    {
        "id": "INC-2026-029", "title": "Checkout errors after certificate rotation", "timestamp": "2026-06-11T08:41:00Z",
        "service": "checkout-api", "severity": "SEV-1", "symptoms": ["payment authorization failures", "checkout 502 rate reached 31%", "database pool wait elevated"],
        "error_signatures": ["x509: certificate signed by unknown authority", "upstream TLS handshake failed"], "deployment": "checkout-2.16.2",
        "configuration_context": "Payment gateway CA bundle rotated; app containers retained old mounted bundle.",
        "actions": [{"action": "Restart one canary pod", "outcome": "inconclusive", "notes": "Canary remained unhealthy; no fleet-wide restart performed."},
                    {"action": "Refresh mounted CA bundle on canary and verify TLS chain", "outcome": "successful", "notes": "Canary authorizations passed; rollout followed after validation."}],
        "confirmed_root_cause": "Stale payment gateway CA certificate bundle in the deployment.", "resolution": "Refresh certificate bundle and roll out after canary verification.", "resolution_minutes": 36,
    },
    {
        "id": "INC-2026-021", "title": "Checkout queue growth after consumer regression", "timestamp": "2026-05-22T13:55:00Z",
        "service": "checkout-api", "severity": "SEV-3", "symptoms": ["checkout confirmation delay", "order queue age rising", "API mostly responsive"],
        "error_signatures": ["consumer heartbeat missed", "retry budget exhausted"], "deployment": "checkout-2.15.0",
        "configuration_context": "Consumer concurrency reduced from 16 to 4 in a config rollout.",
        "actions": [{"action": "Restart API pods", "outcome": "failed", "notes": "Queue age continued increasing."},
                    {"action": "Restore consumer concurrency to 16 and watch queue age", "outcome": "successful", "notes": "Queue drained steadily without error-rate increase."}],
        "confirmed_root_cause": "Consumer concurrency was reduced below incoming order volume.", "resolution": "Restore consumer concurrency to 16.", "resolution_minutes": 42,
    },
]

FIRST_DEMO = {
    "title": "Checkout latency spike with no prior history", "timestamp": "2026-09-28T09:00:00Z",
    "service": "checkout-api", "severity": "SEV-2", "symptoms": ["checkout p95 latency rose to 7.2s", "payment requests intermittently timeout"],
    "error_signatures": ["TimeoutError: upstream request exceeded 5s"], "deployment": "checkout-2.19.0",
    "configuration_context": "Traffic is 2.5x baseline; pool and lock metrics not yet checked.",
}

