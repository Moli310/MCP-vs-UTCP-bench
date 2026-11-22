"""Path B: REST API. UTCP reads /openapi.json and calls these endpoints directly."""
from fastapi import FastAPI

from shared import queries

# servers= puts the base URL in the OpenAPI spec so UTCP knows where to send calls
app = FastAPI(title="IAM SQL API", version="1.0.0",
              servers=[{"url": "http://127.0.0.1:8000"}])


@app.get("/identities/search", operation_id="find_identity")
def find_identity(name: str) -> list[dict]:
    """Search identities by display name (partial match). Returns up to 10."""
    return queries.find_identity(name)


@app.get("/identities/{user_id}/entitlements", operation_id="get_entitlements")
def get_entitlements(user_id: str) -> list[dict]:
    """List the applications and entitlements held by one identity."""
    return queries.get_entitlements(user_id)


@app.get("/accounts/orphaned", operation_id="find_orphaned_accounts")
def find_orphaned_accounts() -> list[dict]:
    """List accounts that are not correlated to any identity."""
    return queries.find_orphaned_accounts()
