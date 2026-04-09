"""Tests for the regex detection engine."""

from shieldprompt.detector.regex_engine import RegexDetector
from shieldprompt.entities import EntityType


def test_email_detection():
    detector = RegexDetector(entities={EntityType.EMAIL_ADDRESS})
    text = "Contact me at john.doe@company.com for details."
    dets = detector.detect(text)
    assert len(dets) == 1
    assert dets[0].entity_type == EntityType.EMAIL_ADDRESS
    assert dets[0].value == "john.doe@company.com"


def test_phone_detection():
    detector = RegexDetector(entities={EntityType.PHONE_NUMBER})
    text = "Call me at (555) 123-4567 or +1 555.987.6543"
    dets = detector.detect(text)
    assert len(dets) == 2


def test_credit_card_detection():
    detector = RegexDetector(entities={EntityType.CREDIT_CARD})
    # Valid Luhn number
    text = "My card is 4111 1111 1111 1111"
    dets = detector.detect(text)
    assert len(dets) == 1
    assert dets[0].entity_type == EntityType.CREDIT_CARD


def test_credit_card_invalid_luhn():
    detector = RegexDetector(entities={EntityType.CREDIT_CARD})
    text = "Not a card: 1234 5678 9012 3456"
    dets = detector.detect(text)
    assert len(dets) == 0


def test_ssn_detection():
    detector = RegexDetector(entities={EntityType.SSN})
    text = "SSN: 123-45-6789"
    dets = detector.detect(text)
    assert len(dets) == 1
    assert dets[0].value == "123-45-6789"


def test_ip_detection():
    detector = RegexDetector(entities={EntityType.IP_ADDRESS})
    text = "Server at 192.168.1.100 and 10.0.0.1"
    dets = detector.detect(text)
    assert len(dets) == 2


def test_url_detection():
    detector = RegexDetector(entities={EntityType.URL})
    text = "Visit https://example.com/path?q=1 for more."
    dets = detector.detect(text)
    assert len(dets) == 1


def test_aws_key_detection():
    detector = RegexDetector(entities={EntityType.AWS_KEY})
    text = "Key: AKIAIOSFODNN7EXAMPLE"
    dets = detector.detect(text)
    assert len(dets) == 1


def test_api_key_detection():
    detector = RegexDetector(entities={EntityType.API_KEY})
    text = "Token: sk-abcdefghijklmnopqrstuvwxyz"
    dets = detector.detect(text)
    assert len(dets) == 1


def test_no_false_positives_on_clean_text():
    detector = RegexDetector()
    text = "The weather is nice today."
    dets = detector.detect(text)
    assert len(dets) == 0


def test_multiple_entities():
    detector = RegexDetector()
    text = "Email alice@test.com, IP 10.0.0.1, SSN 123-45-6789"
    dets = detector.detect(text)
    types = {d.entity_type for d in dets}
    assert EntityType.EMAIL_ADDRESS in types
    assert EntityType.IP_ADDRESS in types
    assert EntityType.SSN in types


def test_entity_filtering():
    detector = RegexDetector(entities={EntityType.EMAIL_ADDRESS})
    text = "Email alice@test.com, IP 10.0.0.1"
    dets = detector.detect(text)
    assert len(dets) == 1
    assert dets[0].entity_type == EntityType.EMAIL_ADDRESS
