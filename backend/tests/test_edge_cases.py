"""Each hard rule fires on its own edge case (seed/edge_cases.py), and the cases stay out of the normal seed."""

import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event
from sqlmodel import Session, SQLModel, func, select

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from seed import edge_cases  # noqa: E402
from seed import seed as seedmod  # noqa: E402

from app.models import Decision, Invoice, Payment, PaymentStatus, Vendor  # noqa: E402
from app.services import risk  # noqa: E402
from tests.helpers import build_context  # noqa: E402


@pytest.fixture(scope="module")
def world(tmp_path_factory, seed_template):
    from tests.conftest import copy_seeded

    engine = create_engine(f"sqlite:///{copy_seeded(seed_template, tmp_path_factory.mktemp('edge'))}")
    s = Session(engine)
    cases = edge_cases.add_edge_cases(s)
    yield s, cases
    s.close()


def assess(s, case):
    inv = s.get(Invoice, case.invoice_id)
    payment, ctx = build_context(s, inv)
    return risk.assess(payment, ctx), ctx


def test_the_normal_seed_has_no_edge_cases(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/n.sqlite")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        seedmod.seed_database(s, write_pdfs=False)
        assert s.exec(select(func.count()).select_from(Invoice).where(Invoice.id.like("inv\\_edge%", escape="\\"))).one() == 0
        assert s.exec(select(func.count()).select_from(Vendor)).one() == 30
        assert s.exec(select(func.count()).select_from(Invoice).where(~Invoice.id.in_(select(Payment.invoice_id)))).one() == 40


def test_four_cases_each_with_one_expected_rule(world):
    _, cases = world
    assert set(cases) == set(edge_cases.EXPECTED_RULES) and len(cases) == 4
    assert {c.name: c.rule for c in cases.values()} == edge_cases.EXPECTED_RULES


@pytest.mark.parametrize("name", list(edge_cases.EXPECTED_RULES))
def test_each_hard_rule_fires_on_its_case_and_only_that_rule(world, name):
    s, cases = world
    case = cases[name]
    a, ctx = assess(s, case)
    assert a.hard_rules_fired == [case.rule], (name, a.reasons)
    assert a.decision in (Decision.controller_review, Decision.hold)  # held, never auto-paid
    assert a.decision != Decision.auto_pay
    assert case.rule in a.hard_rule_actions


def test_new_vendor_under_30_days_with_a_first_payment(world):
    s, cases = world
    a, ctx = assess(s, cases["new_vendor_first_payment"])
    age = (seedmod.ANCHOR - s.get(Vendor, "ven_edge_newleaf").created_at).days
    assert age == 12 < 30 and ctx.prior_payment_count == 0
    assert ctx.requested_destination == ctx.last_verified_destination  # the account matches, so it is not a destination change


def test_invoice_more_than_50_percent_above_the_12_month_max(world):
    s, cases = world
    a, ctx = assess(s, cases["amount_over_max"])
    inv = s.get(Invoice, cases["amount_over_max"].invoice_id)
    assert inv.amount_usd > 1.5 * max(ctx.history_amounts) and inv.amount_usd < 1.7 * max(ctx.history_amounts)
    assert ctx.prior_payment_count > 10 and not ctx.requested_contacts_differ


def test_contact_details_that_differ_from_on_file(world):
    s, cases = world
    a, ctx = assess(s, cases["contacts_differ"])
    assert ctx.requested_contacts_differ is True
    assert "independent numbers" in a.hard_rule_actions["contacts_differ"]
    # the number the vendor already has on file does NOT trigger it
    from app.services.run import contacts_differ

    assert contacts_differ("call us on +1 (415) 555-0101", ["+14155550101"]) is False


def test_true_one_off_rental_vendor(world):
    s, cases = world
    a, ctx = assess(s, cases["one_off_rental"])
    vid = cases["one_off_rental"].vendor_id
    assert s.exec(select(func.count()).select_from(Invoice).where(Invoice.vendor_id == vid)).one() == 1  # a single invoice, ever
    assert ctx.prior_payment_count == 0 and (seedmod.ANCHOR - s.get(Vendor, vid).created_at).days > 30  # old vendor: only the first-payment half fires
    assert a.hard_rules_fired == ["new_vendor"]


def test_edge_pdfs_exist_for_the_new_vendors_only(world):
    s, cases = world
    assert s.get(Invoice, "inv_edge_newleaf").pdf_path and s.get(Invoice, "inv_edge_oneoff").pdf_path
    assert s.get(Invoice, "inv_edge_overmax").pdf_path is None and s.get(Invoice, "inv_edge_contacts").pdf_path is None
