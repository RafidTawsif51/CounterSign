import enum
import uuid
from datetime import date, datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel
from pydantic import Field as PydanticField
from sqlalchemy import JSON, Column, event
from sqlalchemy import Enum as SAEnum
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    """Timezone-aware UTC. SQLModel's datetime column rejects naive values."""
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def id_field(prefix: str) -> Any:
    return Field(default_factory=lambda: new_id(prefix), primary_key=True)


# ---------------------------------------------------------------- enums
# Member name == value so the stored string matches the API string.


class VendorStatus(str, enum.Enum):
    active = "active"
    inactive = "inactive"


class ContactSource(str, enum.Enum):
    on_file = "on_file"
    website = "website"
    listing = "listing"


class RunStatus(str, enum.Enum):
    running = "running"
    completed = "completed"
    failed = "failed"


class PaymentStatus(str, enum.Enum):
    pending = "pending"
    paid = "paid"
    held = "held"
    blocked = "blocked"


class Decision(str, enum.Enum):
    auto_pay = "auto_pay"
    controller_review = "controller_review"
    hold = "hold"
    hold_and_verify = "hold_and_verify"


class CallOutcome(str, enum.Enum):
    confirmed = "confirmed"
    denied = "denied"
    no_answer = "no_answer"
    unclear = "unclear"


class AttackSource(str, enum.Enum):
    console = "console"
    judge = "judge"
    bounty_email = "bounty_email"


class AttackResult(str, enum.Enum):
    caught = "caught"
    missed = "missed"


class ModerationStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    hidden = "hidden"


class AuditActor(str, enum.Enum):
    agent = "agent"
    human = "human"
    system = "system"


def enum_col(enum_cls: type[enum.Enum], nullable: bool = False) -> Column:
    """Enum stored as a VARCHAR, not a native type, so adding a value never needs a migration."""
    return Column(
        SAEnum(
            enum_cls,
            native_enum=False,
            length=32,
            validate_strings=True,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=nullable,
    )


# ---------------------------------------------------------------- signal shape


class Signal(BaseModel):
    """One entry of risk_assessments.signals_json. evidence_id lets /ask cite it."""

    name: str
    weight: int
    detail: str
    evidence_id: str = PydanticField(default_factory=lambda: new_id("evd"))


# ---------------------------------------------------------------- tables


class Vendor(SQLModel, table=True):
    __tablename__ = "vendors"

    id: str = id_field("ven")
    name: str
    trade: str
    email_domain: str
    created_at: datetime = Field(default_factory=utcnow)
    status: VendorStatus = Field(
        default=VendorStatus.active, sa_column=enum_col(VendorStatus)
    )


class VendorBankAccount(SQLModel, table=True):
    """Full history. Only services/verify.py may write this table."""

    __tablename__ = "vendor_bank_accounts"

    id: str = id_field("bac")
    vendor_id: str = Field(foreign_key="vendors.id", index=True)
    routing_hash: str
    account_last4: str
    bank_name: str
    valid_from: datetime
    valid_to: Optional[datetime] = None
    # Points at verification_calls.id. No FK constraint: payments -> this table -> calls -> payments
    # would be a cycle that SQLite cannot create.
    verified_by_call_id: Optional[str] = Field(default=None, index=True)


class VendorContact(SQLModel, table=True):
    """Independent numbers come from website or listing, never email. Only services/verify.py may write."""

    __tablename__ = "vendor_contacts"

    id: str = id_field("con")
    vendor_id: str = Field(foreign_key="vendors.id", index=True)
    phone: str
    source: ContactSource = Field(sa_column=enum_col(ContactSource))
    source_url: Optional[str] = None
    first_seen: datetime = Field(default_factory=utcnow)
    last_verified: Optional[datetime] = None


class Message(SQLModel, table=True):
    __tablename__ = "messages"

    id: str = id_field("msg")
    thread_id: str = Field(index=True)  # thr_...
    vendor_id: Optional[str] = Field(default=None, foreign_key="vendors.id", index=True)
    from_addr: str
    reply_to: Optional[str] = None
    subject: str
    body: str
    received_at: datetime = Field(default_factory=utcnow)
    is_attack: bool = False


class Invoice(SQLModel, table=True):
    __tablename__ = "invoices"

    id: str = id_field("inv")
    # vendor_id, number, amount_usd and due_date are null for an uploaded PDF until extraction fills them.
    vendor_id: Optional[str] = Field(default=None, foreign_key="vendors.id", index=True)
    message_id: Optional[str] = Field(default=None, foreign_key="messages.id", index=True)
    number: Optional[str] = None
    amount_usd: Optional[float] = None
    due_date: Optional[date] = None
    remittance_json: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    pdf_path: Optional[str] = None
    extracted_json: Optional[dict] = Field(default=None, sa_column=Column(JSON))


class PaymentRun(SQLModel, table=True):
    __tablename__ = "payment_runs"

    id: str = id_field("run")
    started_at: datetime = Field(default_factory=utcnow)
    completed_at: Optional[datetime] = None
    status: RunStatus = Field(default=RunStatus.running, sa_column=enum_col(RunStatus))
    totals_json: Optional[dict] = Field(default=None, sa_column=Column(JSON))


class Payment(SQLModel, table=True):
    __tablename__ = "payments"

    id: str = id_field("pay")
    run_id: str = Field(foreign_key="payment_runs.id", index=True)
    invoice_id: str = Field(foreign_key="invoices.id", index=True)
    amount_usd: float
    destination_account_id: Optional[str] = Field(
        default=None, foreign_key="vendor_bank_accounts.id"
    )
    status: PaymentStatus = Field(
        default=PaymentStatus.pending, sa_column=enum_col(PaymentStatus)
    )
    nessie_transfer_id: Optional[str] = None


class RiskAssessment(SQLModel, table=True):
    __tablename__ = "risk_assessments"

    id: str = id_field("ras")
    payment_id: str = Field(foreign_key="payments.id", index=True)
    score: int  # 0-100, capped
    decision: Decision = Field(sa_column=enum_col(Decision))
    hard_rules_fired: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    # List of Signal dicts: {name, weight, detail, evidence_id}
    signals_json: list[dict] = Field(default_factory=list, sa_column=Column(JSON))
    model_version: str


class InjectionFinding(SQLModel, table=True):
    __tablename__ = "injection_findings"

    id: str = id_field("inj")
    invoice_id: Optional[str] = Field(default=None, foreign_key="invoices.id", index=True)
    message_id: Optional[str] = Field(default=None, foreign_key="messages.id", index=True)
    technique: str
    snippet: str
    confidence: float


class VerificationCall(SQLModel, table=True):
    __tablename__ = "verification_calls"

    id: str = id_field("cal")
    payment_id: str = Field(foreign_key="payments.id", index=True)
    contact_id: Optional[str] = Field(default=None, foreign_key="vendor_contacts.id")
    started_at: datetime = Field(default_factory=utcnow)
    outcome: Optional[CallOutcome] = Field(
        default=None, sa_column=enum_col(CallOutcome, nullable=True)
    )
    # List of {speaker, text}
    transcript: Optional[list[dict]] = Field(default=None, sa_column=Column(JSON))
    recording_url: Optional[str] = None


class Attack(SQLModel, table=True):
    __tablename__ = "attacks"

    id: str = id_field("atk")
    attacker_name: str
    source: AttackSource = Field(sa_column=enum_col(AttackSource))
    card: str
    payload_ref: Optional[str] = None  # usually a messages.id or invoices.id
    result: Optional[AttackResult] = Field(
        default=None, sa_column=enum_col(AttackResult, nullable=True)
    )
    created_at: datetime = Field(default_factory=utcnow)
    # Bounty entries wait here until a human approves them for the screen.
    moderation_status: ModerationStatus = Field(
        default=ModerationStatus.pending, sa_column=enum_col(ModerationStatus)
    )
    # What the leaderboard shows, kept on the row so it survives a demo reset that keeps the leaderboard:
    # subject, from_addr, body, has_pdf, amount_usd, outcome, reasons, paid_usd. Not part of the spec's table.
    detail_json: Optional[dict] = Field(default=None, sa_column=Column(JSON))


class AuditLog(SQLModel, table=True):
    """Append-only. Composite primary key (id, at) so it can become a Timescale hypertable."""

    __tablename__ = "audit_log"

    id: str = Field(default_factory=lambda: new_id("aud"), primary_key=True)
    at: datetime = Field(default_factory=utcnow, primary_key=True)
    entity: str
    entity_id: str = Field(index=True)
    actor: AuditActor = Field(sa_column=enum_col(AuditActor))
    action: str
    detail_json: Optional[dict] = Field(default=None, sa_column=Column(JSON))


class Event(SQLModel, table=True):
    """Persisted SSE events so a late client can replay a run. Composite primary key (id, at)."""

    __tablename__ = "events"

    id: str = Field(default_factory=lambda: new_id("evt"), primary_key=True)
    at: datetime = Field(default_factory=utcnow, primary_key=True)
    run_id: Optional[str] = Field(default=None, index=True)
    type: str  # run.started, payment.held, ...
    payload: Optional[dict] = Field(default=None, sa_column=Column(JSON))


# ---------------------------------------------------------------- append-only guard


def _forbid(*_args: Any, **_kwargs: Any) -> None:
    raise RuntimeError("audit_log and events are append-only")


for _cls in (AuditLog, Event):
    event.listen(_cls, "before_update", _forbid)
    event.listen(_cls, "before_delete", _forbid)
