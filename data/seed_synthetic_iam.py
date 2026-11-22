"""Creates a synthetic IAM database (data/iam.db). All data is fake."""
import random
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "iam.db"
random.seed(42)  # same data every run, so results are reproducible

FIRST = ["Ann", "Raj", "Mei", "Omar", "Lena", "Carlos", "Priya", "Tom", "Sara", "Kenji", "Nia", "Ivan"]
LAST = ["Shah", "Lopez", "Chen", "Okafor", "Novak", "Patel", "Kim", "Silva", "Brown", "Ali"]
DEPTS = ["Finance", "HR", "IT", "Claims", "Sales", "Legal"]
APPS = ["Active Directory", "Workday", "Salesforce", "ServiceNow", "SAP", "Okta", "GitHub", "Jira"]
ROLES = ["Read", "Write", "Admin", "Approver", "Auditor"]
ORPHANED_COUNT = 120


def main():
    DB_PATH.unlink(missing_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.executescript("""
        CREATE TABLE identities (user_id TEXT PRIMARY KEY, display_name TEXT,
                                 department TEXT, status TEXT);
        CREATE TABLE applications (app_id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE entitlements (ent_id INTEGER PRIMARY KEY, app_id INTEGER, name TEXT);
        CREATE TABLE accounts (account_id INTEGER PRIMARY KEY, app_id INTEGER,
                               native_id TEXT, user_id TEXT);
        CREATE TABLE account_entitlements (account_id INTEGER, ent_id INTEGER);
        CREATE INDEX idx_accounts_user ON accounts(user_id);
        CREATE INDEX idx_ae_account ON account_entitlements(account_id);
    """)

    users = []
    for i in range(500):
        status = "inactive" if random.random() < 0.08 else "active"
        users.append((f"U{1001 + i}", f"{random.choice(FIRST)} {random.choice(LAST)}",
                      random.choice(DEPTS), status))
    con.executemany("INSERT INTO identities VALUES (?, ?, ?, ?)", users)

    con.executemany("INSERT INTO applications VALUES (?, ?)", list(enumerate(APPS, 1)))

    ents = []
    for app_id, app in enumerate(APPS, 1):
        for r, role in enumerate(ROLES):
            ents.append(((app_id - 1) * len(ROLES) + r + 1, app_id, f"{app} {role}"))
    con.executemany("INSERT INTO entitlements VALUES (?, ?, ?)", ents)

    accounts, acct_id = [], 0
    for user_id, *_ in users:
        for app_id in random.sample(range(1, len(APPS) + 1), k=random.randint(2, 5)):
            acct_id += 1
            accounts.append((acct_id, app_id, f"{user_id.lower()}@app{app_id}", user_id))
    for n in range(ORPHANED_COUNT):  # accounts with no matching identity
        acct_id += 1
        app_id = random.randint(1, len(APPS))
        accounts.append((acct_id, app_id, f"svc_legacy_{n}@app{app_id}", None))
    con.executemany("INSERT INTO accounts VALUES (?, ?, ?, ?)", accounts)

    links = []
    for account_id, app_id, _, _ in accounts:
        base = (app_id - 1) * len(ROLES)
        for r in random.sample(range(len(ROLES)), k=random.randint(1, 3)):
            links.append((account_id, base + r + 1))
    con.executemany("INSERT INTO account_entitlements VALUES (?, ?)", links)

    con.commit()
    con.close()
    print(f"Created {DB_PATH}: {len(users)} identities, {len(accounts)} accounts "
          f"({ORPHANED_COUNT} orphaned), {len(links)} entitlement assignments")


if __name__ == "__main__":
    main()
