from app.comparison import build_comparisons


def test_comparison_exposes_hindsight_provenance_and_outcomes_without_promoting_cause():
    current = {
        "service": "checkout-api", "deployment": "checkout-2.19.0",
        "symptoms": ["checkout timeout", "pool wait elevated"],
        "error_signatures": ["AcquireTimeout"],
    }
    selected = [{
        "incident_id": "INC-2026-041", "date": "2026-08-14T10:32:00Z", "service": "checkout-api",
        "relevance": 0.91,
        "provenance": {"memory_id": "hindsight-doc-041"},
        "evidence_summary": (
            "Symptoms: checkout timeout; pool wait at 100% Error signatures: AcquireTimeout "
            "Deployment/configuration: checkout-2.18.3; pool max_size=20 "
            "Interventions and outcomes: Restart failed; increase pool successful "
            "Confirmed root cause: Connection pool capacity was below demand "
            "Resolution: Raised pool capacity"
        ),
    }]

    comparison = build_comparisons(current, selected)[0]

    assert comparison["incident_id"] == "INC-2026-041"
    assert comparison["memory_id"] == "hindsight-doc-041"
    assert comparison["similarity_terms"]
    assert "Restart failed" in comparison["actions_and_outcomes"]
    assert "increase pool successful" in comparison["actions_and_outcomes"]
    assert "Connection pool capacity" in comparison["confirmed_root_cause"]
    assert "not confirmed" not in comparison["confirmed_root_cause"].lower()


def test_comparison_does_not_claim_similarity_when_no_terms_overlap():
    comparison = build_comparisons(
        {"service": "checkout-api", "symptoms": ["tax allocation mismatch"], "error_signatures": ["TaxInvariant"]},
        [{"incident_id": "INC-HIST", "service": "checkout-api", "evidence_summary": "Symptoms: certificate expired Error signatures: TLS handshake"}],
    )[0]

    assert comparison["similarity_terms"] == []
    assert "no direct symptom/error term overlap" in comparison["why_relevant"]
