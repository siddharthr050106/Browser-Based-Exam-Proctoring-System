"""Tests for the rule engine escalation logic."""

import time
from detection.rule_engine import RuleEngine, Tier


def test_tab_switch_info():
    """Single tab switch → INFO."""
    engine = RuleEngine()
    signal = engine.process_tab_switch("tab_switch")
    assert signal.tier == Tier.INFO


def test_tab_switch_warning():
    """2 tab switches → WARNING."""
    engine = RuleEngine()
    engine.process_tab_switch("tab_switch")
    signal = engine.process_tab_switch("tab_switch")
    assert signal.tier == Tier.WARNING


def test_tab_switch_flag():
    """3+ tab switches in 2 min → FLAG."""
    engine = RuleEngine()
    engine.process_tab_switch("tab_switch")
    engine.process_tab_switch("tab_switch")
    signal = engine.process_tab_switch("tab_switch")
    assert signal.tier == Tier.FLAG
    assert signal.requires_clip is True


def test_phone_detected_flag():
    """Phone detected → immediate FLAG."""
    engine = RuleEngine()
    signals = engine.process_yolo(["PHONE_DETECTED"])
    assert len(signals) == 1
    assert signals[0].tier == Tier.FLAG
    assert signals[0].event_type == "phone_detected"


def test_multiple_persons_flag():
    """Multiple persons → immediate FLAG."""
    engine = RuleEngine()
    signals = engine.process_yolo(["MULTIPLE_PERSONS"])
    assert len(signals) == 1
    assert signals[0].tier == Tier.FLAG


def test_identity_mismatch_critical():
    """Identity mismatch → CRITICAL."""
    engine = RuleEngine()
    signals = engine.process_face_gate(["IDENTITY_MISMATCH"])
    assert len(signals) == 1
    assert signals[0].tier == Tier.CRITICAL


def test_background_change_flag():
    """Background change → FLAG."""
    engine = RuleEngine()
    signals = engine.process_background(["BACKGROUND_CHANGED"], ssim_score=0.65)
    assert len(signals) == 1
    assert signals[0].tier == Tier.FLAG


def test_gaze_anomaly_tiers():
    """Gaze anomaly score determines tier."""
    engine = RuleEngine()

    # High score → FLAG
    signals = engine.process_gaze_anomaly(["GAZE_ANOMALY"], score=0.85)
    assert signals[0].tier == Tier.FLAG

    # Medium score → WARNING
    signals = engine.process_gaze_anomaly(["GAZE_ANOMALY"], score=0.6)
    assert signals[0].tier == Tier.WARNING


def test_no_face_flag():
    """No face → FLAG."""
    engine = RuleEngine()
    signals = engine.process_face_gate(["NO_FACE"])
    assert len(signals) == 1
    assert signals[0].tier == Tier.FLAG


def test_composite_critical():
    """Multiple FLAG events within 1 minute → CRITICAL."""
    engine = RuleEngine()
    s1 = engine.process_yolo(["PHONE_DETECTED"])[0]
    engine.check_composite_critical(s1)

    s2 = engine.process_gaze_anomaly(["GAZE_ANOMALY"], score=0.85)[0]
    composite = engine.check_composite_critical(s2)

    assert composite is not None
    assert composite.tier == Tier.CRITICAL
