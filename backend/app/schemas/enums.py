import enum


class Verdict(str, enum.Enum):
    SATISFIED = "SATISFIED"
    VIOLATION = "VIOLATION"
    NOT_VERIFIED = "NOT_VERIFIED"
    CONFLICT = "CONFLICT"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class RiskLevel(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class DecisionType(str, enum.Enum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    SEND_FOR_CLARIFICATION = "SEND_FOR_CLARIFICATION"


class DocumentType(str, enum.Enum):
    TENDER = "TENDER"
    PAN = "PAN"
    GST = "GST"
    UDYAM = "UDYAM"
    FINANCIAL = "FINANCIAL"
    OEM_AUTHORIZATION = "OEM_AUTHORIZATION"
    LOCAL_CONTENT = "LOCAL_CONTENT"
    OTHER = "OTHER"



class OfficerRole(str, enum.Enum):
    ADMIN = "ADMIN"
    INSPECTOR = "INSPECTOR"
    VIEWER = "VIEWER"
