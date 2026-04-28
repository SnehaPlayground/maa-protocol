from dataclasses import dataclass

@dataclass
class Claim:
    subject: str
    resource: str
    action: str

CLAIMS: list[Claim] = []

def grant(subject: str, resource: str, action: str):
    claim = Claim(subject, resource, action)
    CLAIMS.append(claim)
    return claim

def list_claims():
    return CLAIMS
