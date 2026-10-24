"""A transfer to a bank account that was created after setup-nessie creates the Nessie account first."""

import asyncio

import pytest
from sqlmodel import Session

from app.config import Settings
from sqlalchemy import create_engine

from app import db
from app.models import Vendor, VendorBankAccount
from app.services import payments


class FakeNessie:
    """An in-memory Nessie: customers, accounts (by nickname) and transfers. Records every call."""

    def __init__(self):
        self.accounts, self.customers, self.transfers, self.calls = [], [], [], []

    def __call__(self, method, path, **kwargs):
        self.calls.append((method, path))
        if (method, path) == ("GET", "/accounts"):
            return list(self.accounts)
        if (method, path) == ("POST", "/customers"):
            c = {"_id": f"cust{len(self.customers)}"}
            self.customers.append(c)
            return {"objectCreated": c}
        if method == "POST" and path.startswith("/customers/") and path.endswith("/accounts"):
            a = {"_id": f"acct{len(self.accounts)}", "nickname": kwargs["json"]["nickname"], "balance": kwargs["json"]["balance"]}
            self.accounts.append(a)
            return {"objectCreated": a}
        if method == "POST" and path.endswith("/transfers"):
            t = {"_id": f"tr{len(self.transfers)}", "payee": path.split("/")[2], **kwargs["json"]}
            self.transfers.append(t)
            return {"objectCreated": t}
        raise AssertionError(f"unexpected Nessie call {method} {path}")


@pytest.fixture
def nessie(monkeypatch, tmp_path):
    from sqlmodel import SQLModel

    private = create_engine(f"sqlite:///{tmp_path}/nessie.sqlite")  # the transfer code reads db.engine at call time
    monkeypatch.setattr(db, "engine", private)
    fake = FakeNessie()
    monkeypatch.setattr(payments, "_nessie", fake)
    monkeypatch.setattr(payments, "get_settings", lambda: Settings(mock_nessie=False, nessie_api_key="test-key"))
    monkeypatch.setattr(payments, "_account_cache", {})
    SQLModel.metadata.create_all(private)
    with Session(private) as s:
        v = Vendor(id="ven_nessie_t", name="Summit Concrete", trade="concrete", email_domain="summitconcrete.com")
        s.add(v)
        s.merge(VendorBankAccount(id="bac_nessie_new", vendor_id=v.id, routing_hash="h", account_last4="6213", bank_name="Harborline Bank", valid_from=v.created_at))
        s.commit()
    return fake


def send(account_id):
    return asyncio.run(payments.create_transfer(account_id, 1234.5, "Invoice SUM-1253"))


def test_a_bank_account_created_after_setup_gets_its_nessie_account_and_the_transfer_is_real(nessie):
    t = send("bac_nessie_new")
    assert t.mode == "nessie" and str(t) == "tr0"  # a real sandbox transfer, not a mock id
    assert [a["nickname"] for a in nessie.accounts] == ["bac_nessie_new"] and nessie.accounts[0]["balance"] == 0
    assert nessie.customers and nessie.transfers[0]["payee"] == "acct0" and nessie.transfers[0]["amount"] == 1234.5


def test_the_account_is_created_once(nessie):
    send("bac_nessie_new")
    send("bac_nessie_new")
    assert len(nessie.accounts) == 1 and len(nessie.transfers) == 2


def test_an_account_that_already_exists_in_nessie_is_reused(nessie):
    nessie.accounts.append({"_id": "existing", "nickname": "bac_nessie_new"})
    send("bac_nessie_new")
    assert len(nessie.accounts) == 1 and nessie.transfers[0]["payee"] == "existing" and not any(c[1] == "/customers" for c in nessie.calls)


def test_an_id_that_is_not_one_of_our_bank_accounts_is_not_created_and_falls_back_visibly(nessie):
    t = send("bac_someone_elses")
    assert t.mode == "mock_fallback" and nessie.accounts == [] and nessie.transfers == []
    assert "not a known bank account" in t.error


def test_a_nessie_failure_while_creating_the_account_still_falls_back_and_says_so(nessie, monkeypatch):
    def down(method, path, **kw):
        raise RuntimeError("Nessie POST /customers failed: HTTPStatusError (500)")

    monkeypatch.setattr(payments, "_nessie", down)
    t = send("bac_nessie_new")
    assert t.mode == "mock_fallback" and "500" in t.error
