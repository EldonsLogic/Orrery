"""SEC-019 business action admission, separate from Blueprint runtime policies."""
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal
from fractions import Fraction
from hashlib import sha256
from hmac import compare_digest
import json
import re
from typing import Any, Callable

from .action_policy_store import ActionAudit, ActionPolicyStore, Principal, valid_instant

_DECIMAL = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?")
# Minor-unit exponents for the currencies supported by the platform simulator.
_CURRENCY_PRECISION = {
    "SAR": 2, "AED": 2, "EGP": 2, "QAR": 2, "USD": 2, "EUR": 2, "GBP": 2,
    "KWD": 3, "BHD": 3, "OMR": 3, "JOD": 3,
}
_MAX_SAFE_INT = 2**53 - 1


def _decimal(value: object) -> Decimal:
    if type(value) is not str or len(value) > 64 or not _DECIMAL.fullmatch(value):
        raise ValueError("Expected decimal text")
    return Decimal(value)


def _ordered(value: object) -> object:
    if type(value) is dict and all(type(key) is str for key in value):
        return {key: _ordered(value[key]) for key in sorted(value, key=lambda key: key.encode("utf-16be"))}
    if type(value) is list:
        return [_ordered(item) for item in value]
    if value is None or type(value) in (str, bool) or type(value) is int and abs(value) <= _MAX_SAFE_INT:
        return value
    raise ValueError("Expected a JSON value in the action-policy profile")


def canonical_json(value: object) -> bytes:
    """Encode the RFC 8785 subset used by actions, with safe integers and no floats."""
    return json.dumps(_ordered(value), ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")


@dataclass(frozen=True)
class ActionRequest:
    """Untrusted action data. Revisions map each target record ID to the reviewed revision."""

    tenant_id: str
    request_id: str
    action_id: str
    action_version: int
    table_version: str
    idempotency_key: str
    payload: dict
    target_revisions: dict
    break_glass_reason: str | None = None


def payload_hash(request: ActionRequest, initiator_id: str) -> str:
    """Bind the full material payload and execution envelope to the authenticated initiator."""
    for field in ("total", "amount"):
        if field in request.payload:
            _decimal(request.payload[field])
    for line in request.payload.get("lines", []):
        if type(line) is dict:
            for field in ("price", "discount", "quantity"):
                if field in line and (field != "quantity" or type(line[field]) is not int):
                    _decimal(line[field])
    binding = asdict(request)
    del binding["break_glass_reason"]
    binding["initiator_id"] = initiator_id
    return "sha256:" + sha256(canonical_json(binding)).hexdigest()


@dataclass(frozen=True)
class Approval:
    """An authoritative approval record with the approver's currently resolved identity."""

    id: str
    tenant_id: str
    action_id: str
    table_version: str
    payload_hash: str
    approver: Principal
    expires_at: datetime
    status: str
    step_up: bool = False


@dataclass(frozen=True)
class ActionContext:
    """Current authority for this exact request, resolved server-side from its session."""

    tenant_id: str
    request_id: str
    action_id: str
    submitter: Principal
    drafter: Principal
    in_scope: bool
    active: bool
    approvals: tuple[Approval, ...] = ()
    editor_ids: frozenset[str] = frozenset()
    approvals_required: int | None = None
    threshold: str | None = None
    amount: str | None = None
    currency: str | None = None
    break_glass_until: datetime | None = None
    break_glass_step_up: bool = False
    # Q-41, Q-563: role name -> ids of every human in the tenant who holds it now, including people
    # who are away or suspended (role holding, not availability). Server-resolved, never from a payload.
    # None or malformed means no sole-owner fallback.
    tenant_role_holders: dict | None = None


@dataclass(frozen=True)
class PolicyRow:
    """Platform action rule. Tenant settings can only tighten its controls."""

    action_id: str
    initiators: frozenset[str]
    approvers: frozenset[str]
    floor: bool
    required_fields: tuple[str, ...]
    approvals: int = 0
    threshold_approval: bool = False
    author_sod: bool = False
    step_up: bool = False
    break_glass: bool = False
    version: int = 1
    cap: str | None = None
    enabled: bool = True


@dataclass(frozen=True)
class PolicyTable:
    """Versioned platform rules and the currency of any configured caps."""

    version: str
    rows: tuple[PolicyRow, ...]
    currency: str | None = None


# Rows that need a different approver and are R1 to R3 (Q-41, Q-563). An allow-list, so a new row
# never gets the sole-owner fallback by default; R4 rows (AP-FIN-02, AP-PERM-01, AP-BPL-01) stay out.
_SOLE_OWNER_ROWS = frozenset({"AP-STOCK-01", "AP-FIN-01"})
_OWNER = frozenset({"owner", "tenant_admin"})
_FINANCE = frozenset({"finance"})
_ROWS = (
    PolicyRow("AP-SALES-01", _OWNER | {"sales"}, _OWNER, False, ("customer", "lines", "total", "currency")),
    # These IDs have no executable policy in SEC-019. Blueprint publish has its own review path.
    PolicyRow("AP-SALES-02", frozenset(), frozenset(), False, (), enabled=False),
    PolicyRow("AP-PAY-01", frozenset(), frozenset(), True, (), enabled=False),
    PolicyRow("AP-BPL-01", frozenset(), frozenset(), True, (), enabled=False),
    PolicyRow("AP-STOCK-01", _OWNER | {"warehouse"}, _OWNER, True, ("order_id", "warehouse", "lines"),
              threshold_approval=True, break_glass=True),
    PolicyRow("AP-FIN-01", _FINANCE, _OWNER, True, ("delivery_ids", "customer", "lines", "total", "currency"),
              threshold_approval=True, author_sod=True, step_up=True, break_glass=True),
    PolicyRow("AP-FIN-02", _FINANCE, _OWNER, True, ("invoice_id", "reason", "total", "currency"),
              approvals=1, step_up=True),
    PolicyRow("AP-PERM-01", _OWNER, _OWNER, True,
              ("target_user", "roles_before", "roles_after", "scopes", "limits_before", "limits_after"),
              approvals=1, step_up=True),
)


def starter_table(
    *, version: str = "sec-019-v1", stock_cap: str | None = None, invoice_cap: str | None = None,
    currency: str | None = None,
) -> PolicyTable:
    """Load SEC-019 engine rules. Undeclared actions have no executable row."""
    caps = {"AP-STOCK-01": stock_cap, "AP-FIN-01": invoice_cap}
    return PolicyTable(version, tuple(replace(row, cap=caps.get(row.action_id)) for row in _ROWS), currency)


def _identifier(value: object) -> str | None:
    return value if type(value) is str and 0 < len(value) <= 256 and value.strip() else None


class _Denied(Exception):
    """Internal decision code suitable for the audit journal."""


def _require(condition: object, reason: str) -> None:
    if not condition:
        raise _Denied(reason)


def _money(value: object, currency: object) -> Decimal:
    """Validate non-negative monetary text at the currency's scale without rounding."""
    _require(type(currency) is str and currency in _CURRENCY_PRECISION, "invalid_currency")
    amount = _decimal(value)
    _require(not amount.is_signed() and -amount.as_tuple().exponent <= _CURRENCY_PRECISION[currency],
             "invalid_money")
    return amount


def _validated_rows(table: PolicyTable) -> dict[str, PolicyRow]:
    _require(type(table) is PolicyTable and _identifier(table.version) and type(table.rows) is tuple,
             "invalid_table")
    _require(table.currency is None or type(table.currency) is str and table.currency in _CURRENCY_PRECISION,
             "invalid_table")
    rows = {row.action_id: row for row in table.rows}
    _require(len(rows) == len(table.rows) == len(_ROWS), "invalid_table")
    for baseline in _ROWS:
        row = rows.get(baseline.action_id)
        _require(type(row) is PolicyRow and type(row.enabled) is bool and type(row.floor) is bool and type(row.approvals) is int
                 and type(row.version) is int and replace(row, cap=None) == baseline, "invalid_table")
        if row.cap is not None:
            _require(row.threshold_approval, "invalid_table")
            _money(row.cap, table.currency)
    return rows


def _check_identity(actor: object, *, submitter: bool = False) -> bool:
    if (type(actor) is not Principal or not _identifier(actor.id) or type(actor.roles) is not frozenset
            or not all(map(_identifier, actor.roles))):
        return False
    if submitter and not actor.roles:
        return False
    return (actor.kind == "human" and actor.owner_id is None
            or actor.kind == "agent" and bool(_identifier(actor.owner_id)))


def _check_payload(request: ActionRequest, row: PolicyRow) -> None:
    payload = request.payload
    _require(type(payload) is dict and all(field in payload for field in row.required_fields), "invalid_payload")
    targets = request.target_revisions
    _require(type(targets) is dict and bool(targets) and all(
        _identifier(key) and (type(rev) is int and rev >= 0 or _identifier(rev))
        for key, rev in targets.items()
    ), "invalid_revisions")

    for field in ("order_id", "target_user", "invoice_id"):
        if field in payload:
            _require(_identifier(payload[field]) and payload[field] in targets, "invalid_revisions")
    if row.action_id == "AP-SALES-01":
        _require(_identifier(payload["customer"]) and payload["customer"] in targets, "invalid_revisions")
    if row.action_id == "AP-FIN-01":
        ids = payload["delivery_ids"]
        _require(_identifier(payload["customer"]) and type(ids) is list and bool(ids)
                 and all(_identifier(key) and key in targets for key in ids), "invalid_revisions")

    currency = payload.get("currency")
    if "currency" in payload:
        _require(type(currency) is str and currency in _CURRENCY_PRECISION, "invalid_currency")
    total = _money(payload["total"], currency) if "total" in payload else None
    for field in ("amount", "discount"):
        if field in payload:
            _money(payload[field], currency)
    if "lines" in payload:
        lines = payload["lines"]
        _require(type(lines) is list and bool(lines), "invalid_lines")
        line_total = Fraction(0)
        priced = row.action_id != "AP-STOCK-01" or total is not None
        for line in lines:
            _require(type(line) is dict and _identifier(line.get("item")), "invalid_lines")
            quantity = line.get("quantity")
            quantity = quantity if type(quantity) is int else _decimal(quantity)
            _require(quantity > 0, "invalid_quantity")
            if priced or "price" in line or "discount" in line:
                price = _money(line.get("price"), currency)
                discount = _money(line.get("discount"), currency)
                # Discount is an absolute line amount. Fractions keep the exact
                # product and sum independent of the ambient Decimal context.
                net = Fraction(quantity) * Fraction(price) - Fraction(discount)
                _require(net >= 0, "invalid_money")
                line_total += net
        if total is not None:
            _require(Fraction(total) == line_total, "total_mismatch")


def _bound_amount(context: ActionContext, payload: dict, field: str) -> Decimal:
    """Compare the request amount with the amount resolved from engine state."""
    _require(context.currency == payload.get("currency"), "invalid_amount")
    amount = _money(context.amount, context.currency)
    _require(amount == _money(payload.get(field), context.currency), "invalid_amount")
    return amount


def _minimum_approvals(
    row: PolicyRow, table: PolicyTable, context: ActionContext, request: ActionRequest,
) -> int:
    if not row.threshold_approval:
        return row.approvals
    amount_field = "total" if row.action_id == "AP-FIN-01" else "amount"
    amount = None
    if context.amount is not None or amount_field in request.payload:
        amount = _bound_amount(context, request.payload, amount_field)
    if context.threshold is None:
        return 1
    _require(row.cap is not None and amount is not None and context.currency == table.currency,
             "invalid_threshold")
    threshold = _money(context.threshold, context.currency)
    _require(threshold <= _money(row.cap, table.currency), "invalid_threshold")
    return int(amount > threshold)


def _check_permission_change(
    request: ActionRequest, context: ActionContext, table: PolicyTable, rows: dict[str, PolicyRow],
) -> None:
    target = request.payload["target_user"]
    _require(target not in {context.submitter.id, context.drafter.id, context.drafter.owner_id}, "self_target")
    previous_limits = request.payload["limits_before"]
    limits = request.payload["limits_after"]
    _require(type(previous_limits) is dict and type(limits) is dict, "invalid_limits")
    if previous_limits or limits:
        _require(context.currency == request.payload.get("currency") == table.currency, "invalid_limits")
    for limit in previous_limits.values():
        _money(limit, table.currency)
    for action_id, limit in limits.items():
        rule = rows.get(action_id)
        _require(rule is not None and rule.cap is not None
                 and _money(limit, table.currency) <= _money(rule.cap, table.currency), "invalid_limits")


def _sole_owner(
    row: PolicyRow, context: ActionContext, approval: Approval, required: int,
) -> bool:
    """Q-41 and Q-563: the tenant owner is the only human holding any approving role of this R1 to R3 row."""
    actor, holders = approval.approver, context.tenant_role_holders
    if (row.action_id not in _SOLE_OWNER_ROWS or required != 1 or approval.step_up is not True
            or "owner" not in actor.roles or type(holders) is not dict
            or not all(role in holders for role in row.approvers)):
        return False
    people = [holders[role] for role in row.approvers]
    return (all(type(group) is frozenset and all(map(_identifier, group)) for group in people)
            and frozenset().union(*people) == {actor.id})


def _approve(
    row: PolicyRow, request: ActionRequest, context: ActionContext, digest: str, required: int, now: datetime,
) -> tuple[tuple[str, ...], bool]:
    _require(type(context.approvals) is tuple and len(context.approvals) == required, "approval_count")
    excluded = {context.submitter.id, context.drafter.id, context.drafter.owner_id}
    if row.author_sod:
        _require(type(context.editor_ids) is frozenset and all(map(_identifier, context.editor_ids)),
                 "invalid_edit_history")
        excluded.update(context.editor_ids)
    if row.action_id == "AP-PERM-01":
        excluded.add(request.payload["target_user"])
    tokens = []
    self_approved = False
    for approval in context.approvals:
        _require(type(approval) is Approval and _identifier(approval.id) and approval.id not in tokens
                 and approval.tenant_id == request.tenant_id and approval.action_id == request.action_id
                 and approval.table_version == request.table_version and approval.status == "approved"
                 and compare_digest(approval.payload_hash, digest)
                 and valid_instant(approval.expires_at) and approval.expires_at > now, "invalid_approval")
        actor = approval.approver
        _require(_check_identity(actor, submitter=True) and actor.kind == "human"
                 and actor.roles & row.approvers and (not row.step_up or approval.step_up is True),
                 "ineligible_approver")
        if actor.id in excluded:
            # Only the sole-owner fallback may lift the submitter, agent-owner and editor exclusions.
            _require(_sole_owner(row, context, approval, required), "ineligible_approver")
            self_approved = True
        excluded.add(actor.id)
        tokens.append(approval.id)
    return tuple(tokens), self_approved


@dataclass(frozen=True)
class AuthorizedAction:
    """The reviewed action snapshot and identity to use for the single engine effect."""

    request: ActionRequest
    submitter_id: str
    self_approved: bool = False

    @property
    def payload(self) -> dict:
        return self.request.payload


class ActionEffectFailed(Exception):
    """A handler confirms it had no durable effect, including after a verified rollback."""


class ActionPolicyEnforcer:
    """Verify the trusted state and durably admit an exact snapshot before any effect."""

    def __init__(
        self,
        load_table: Callable[[], PolicyTable],
        resolve: Callable[[str, ActionRequest], ActionContext | None],
        store: ActionPolicyStore,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ):
        # Resolve scope, current memberships, active request/approval status, and monetary
        # facts for this snapshot from authenticated server state, never from payload metadata.
        self._load_table = load_table
        self._resolve = resolve
        self.store = store
        self._clock = clock

    def authorize(
        self, session: str, request: ActionRequest, *, session_tenant_id: str | None,
        handler_available: bool = True,
    ) -> AuthorizedAction | None:
        """Return an admission only after its audit and replay claims commit."""
        context = None
        digest = None
        now = None
        expires_at = None
        tokens: tuple[str, ...] = ()
        self_approved = False
        decision, reason = "deny", "policy_unavailable"
        envelope = request if type(request) is ActionRequest else None
        try:
            now = self._clock()
            _require(valid_instant(now), "clock_unavailable")
            _require(envelope is not None and _identifier(session) and all(map(_identifier, (
                request.tenant_id, request.request_id, request.action_id, request.table_version,
                request.idempotency_key,
            ))), "invalid_request")
            _require(_identifier(session_tenant_id) and request.tenant_id == session_tenant_id, "tenant_mismatch")
            request = replace(request, payload=json.loads(canonical_json(request.payload)),
                              target_revisions=json.loads(canonical_json(request.target_revisions)))
            resolved = self._resolve(session, request)
            _require(type(resolved) is ActionContext and (resolved.tenant_id, resolved.request_id, resolved.action_id)
                     == (session_tenant_id, request.request_id, request.action_id), "unresolved_request")
            context = resolved
            _require(_check_identity(context.submitter, submitter=True) and _check_identity(context.drafter),
                     "unresolved_identity")
            digest = payload_hash(request, context.submitter.id)
            table = self._load_table()
            rows = _validated_rows(table)
            row = rows.get(request.action_id)
            _require(row is not None and row.enabled and request.table_version == table.version
                     and type(request.action_version) is int and request.action_version == row.version, "policy_mismatch")
            _require(context.active is True and context.in_scope is True, "request_unavailable")
            _require(context.submitter.kind == "human", "human_required")
            _require(handler_available is True, "operation_unavailable")
            _check_payload(request, row)
            if row.action_id == "AP-FIN-02":
                # Cancellation carries the engine's correcting-entry preview
                # magnitude. There are no signed credit inputs in the starter table.
                _bound_amount(context, request.payload, "total")
            if row.action_id == "AP-PERM-01":
                _check_permission_change(request, context, table, rows)
            required = _minimum_approvals(row, table, context, request)
            if context.approvals_required is not None:
                extra = context.approvals_required
                _require(type(extra) is int and required <= extra <= 2, "invalid_approval_control")
                required = extra

            if request.break_glass_reason is not None:
                reason_text = request.break_glass_reason
                _require(row.break_glass and {"owner", "break_glass"} <= context.submitter.roles
                         and context.break_glass_step_up is True and valid_instant(context.break_glass_until)
                         and context.break_glass_until > now and _identifier(reason_text), "break_glass_denied")
                expires_at = context.break_glass_until
                decision, reason = "break_glass", reason_text.strip()
            else:
                _require(context.submitter.roles & row.initiators, "initiator_denied")
                tokens, self_approved = _approve(row, request, context, digest, required, now)
                expires_at = min((approval.expires_at for approval in context.approvals), default=None)
                decision, reason = "allow", "policy_satisfied"
        except _Denied as exc:
            reason = str(exc)
        except Exception:
            pass

        try:
            audit = self.store.record(self._audit(envelope, context, digest, now, decision, reason,
                                                  self_approved and decision == "allow"),
                                      request.idempotency_key if envelope else None, tokens,
                                      expires_at=expires_at, clock=self._clock)
            if audit.decision != "deny":
                return AuthorizedAction(request, context.submitter.id, audit.self_approved)
        except Exception:
            # A decision that cannot be durably recorded never reaches the engine.
            return None
        return None

    def execute_admitted(
        self, action: AuthorizedAction, run_as_caller: Callable[[Callable[[Any], Any]], Any],
        handler: Callable[[Any, AuthorizedAction], Any],
    ) -> Any:
        """Run a durably admitted action once and append its observed outcome."""
        status = "failed"

        def effect(engine: Any) -> Any:
            nonlocal status
            status = "unknown"
            try:
                return handler(engine, action)
            except ActionEffectFailed:
                status = "failed"
                raise

        try:
            result = run_as_caller(effect)
            status = "applied"
            return result
        finally:
            self.store.record_outcome(action.request.tenant_id, action.request.request_id, status)

    @staticmethod
    def _audit(
        request: ActionRequest | None, context: ActionContext | None, digest: str | None,
        now: datetime | None, decision: str, reason: str, self_approved: bool = False,
    ) -> ActionAudit:
        """Record authenticated identities even on a refusal, without copying untrusted payload fields."""
        def actor(field: str) -> Principal | None:
            principal = getattr(context, field, None)
            return principal if _check_identity(principal) else None

        approvals = context.approvals if context and type(context.approvals) is tuple else ()
        return ActionAudit(
            tenant_id=_identifier(getattr(request, "tenant_id", None)),
            request_id=_identifier(getattr(request, "request_id", None)),
            action_id=_identifier(getattr(request, "action_id", None)),
            action_version=request.action_version if request and type(request.action_version) is int else None,
            table_version=_identifier(getattr(request, "table_version", None)),
            payload_hash=digest,
            drafter=actor("drafter"),
            submitter=actor("submitter"),
            approvers=tuple(approval.approver for approval in approvals if type(approval) is Approval
                            and request and approval.tenant_id == request.tenant_id
                            and _check_identity(approval.approver)) if decision != "break_glass" else (),
            timestamp=now if valid_instant(now) else datetime.now(timezone.utc),
            decision=decision,
            reason=reason,
            break_glass=decision == "break_glass",
            self_approved=self_approved,
        )
