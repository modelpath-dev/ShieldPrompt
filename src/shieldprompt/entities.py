"""Supported PII entity types and their categories."""

from enum import Enum


class EntityType(str, Enum):
    # Regex-detected (deterministic)
    EMAIL_ADDRESS = "EMAIL_ADDRESS"
    PHONE_NUMBER = "PHONE_NUMBER"
    CREDIT_CARD = "CREDIT_CARD"
    SSN = "SSN"
    IP_ADDRESS = "IP_ADDRESS"
    IBAN = "IBAN"
    DATE_OF_BIRTH = "DATE_OF_BIRTH"
    URL = "URL"
    AWS_KEY = "AWS_KEY"
    API_KEY = "API_KEY"

    # NER-detected (contextual)
    PERSON = "PERSON"
    ORGANIZATION = "ORGANIZATION"
    LOCATION = "LOCATION"
    DATE = "DATE"
    MONEY = "MONEY"


REGEX_ENTITIES = {
    EntityType.EMAIL_ADDRESS,
    EntityType.PHONE_NUMBER,
    EntityType.CREDIT_CARD,
    EntityType.SSN,
    EntityType.IP_ADDRESS,
    EntityType.IBAN,
    EntityType.DATE_OF_BIRTH,
    EntityType.URL,
    EntityType.AWS_KEY,
    EntityType.API_KEY,
}

NER_ENTITIES = {
    EntityType.PERSON,
    EntityType.ORGANIZATION,
    EntityType.LOCATION,
    EntityType.DATE,
    EntityType.MONEY,
}

ALL_ENTITIES = REGEX_ENTITIES | NER_ENTITIES

DEFAULT_ENTITIES = {
    EntityType.EMAIL_ADDRESS,
    EntityType.PHONE_NUMBER,
    EntityType.CREDIT_CARD,
    EntityType.SSN,
    EntityType.IP_ADDRESS,
    EntityType.AWS_KEY,
    EntityType.API_KEY,
    EntityType.PERSON,
    EntityType.ORGANIZATION,
    EntityType.LOCATION,
}
