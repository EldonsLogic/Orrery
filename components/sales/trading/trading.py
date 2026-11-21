"""ERP-011: configure native trading documents in the current authenticated site.

Internal library only: the trusted host supplies its request-bound engine module.
No RPC registration, role selection, site switching, commits or financial arithmetic.
Each operation writes one document using normal native permission and validation hooks.
"""
from decimal import Decimal
import re
from unicodedata import category


class TradingError(ValueError):
    """Stable i18n key; the platform renders it using strings.json."""

    def __init__(self, key, *, reason=None):
        """Keep the renderable key separate from safe, non-customer diagnostic codes."""
        super().__init__(key)
        self.reason = reason


def _text(value):
    """Accept bounded Arabic/English record names as data, excluding control characters."""
    if (not isinstance(value, str) or not value or value != value.strip()
            or len(value) > 140 or any(category(c).startswith('C') for c in value)):
        raise TradingError('TRD-TEXT')
    return value


def _number(value, *, percent=False, zero=False):
    """Validate an explicit decimal without float conversion, rounding or money maths."""
    if not isinstance(value, str) or not re.fullmatch(r'[0-9]{1,12}(\.[0-9]{1,9})?', value):
        raise TradingError('TRD-NUMBER', reason='expected_decimal_string')
    number = Decimal(value)
    if number < 0 or (number == 0 and not zero) or (percent and number > 100):
        raise TradingError('TRD-NUMBER', reason='outside_allowed_range')
    return value


_CREDIT_ROLES = frozenset({'Credit Controller', 'Accounts Manager', 'System Manager'})


class TradingPack:
    """Bind to a trusted engine request; all reads and writes retain caller permissions.

    Callers own the surrounding transaction and existing approval/audit boundary. This
    library neither accepts a tenant/actor/role from input nor grants their permissions.
    Do not expose engine injection to RPC or invoke this with a privileged service user.
    """

    def __init__(self, engine):
        self.engine = engine
        self.site = engine.local.site
        self.user = engine.session.user
        self._context()

    def _context(self):
        if (not self.site or not self.user or self.user == 'Guest'
                or self.engine.local.site != self.site or self.engine.session.user != self.user):
            raise TradingError('TRD-CONTEXT')

    def _require_credit_role(self):
        """Require a current credit-management role; fail closed on role-store errors."""
        self._context()
        try:
            roles = self.engine.get_roles(self.user)
        except Exception:
            # Role-store failures must neither grant access nor leak engine details.
            raise TradingError('TRD-ROLE') from None
        self._context()
        if (not isinstance(roles, (list, tuple, set, frozenset))
                or not any(isinstance(role, str) and role in _CREDIT_ROLES for role in roles)):
            raise TradingError('TRD-ROLE')

    def _doc(self, doctype, name, action='read'):
        self._context()
        doc = self.engine.get_doc(doctype, _text(name))
        doc.check_permission(action)
        return doc

    def _fields(self, doc, names, *, write=True, doctype=None):
        # Native save may silently restore hidden fields; refuse instead of reporting success.
        meta = self.engine.get_meta(doctype) if doctype else None
        for name in names:
            df = meta.get_field(name) if meta else None
            for action in (('read', 'write') if write else ('read',)):
                if not doc.has_permlevel_access_to(name, df=df, permission_type=action):
                    raise TradingError('TRD-FIELD')

    def _save(self, doc, *, create=False):
        self._context()
        doc.check_permission('create' if create else 'write')
        saved = doc.insert() if create else doc.save()
        return saved.name

    def _create(self, doctype, values, *, children=()):
        doc = self.engine.new_doc(doctype)
        self._fields(doc, values)
        for child_doctype, child_fields in children:
            self._fields(doc, child_fields, doctype=child_doctype)
        doc.update(values)
        return self._save(doc, create=True)

    def _price_list(self, name):
        settings = self._doc('Selling Settings', 'Selling Settings')
        doc = self._doc('Price List', name)
        if (settings.get('editable_price_list_rate') != 0
                or doc.get('selling') != 1 or doc.get('enabled') != 1):
            raise TradingError('TRD-PRICE')
        return doc

    def enforce_price_lists(self):
        """Disable manual list-rate editing; preserve every other selling setting."""
        doc = self._doc('Selling Settings', 'Selling Settings', 'write')
        self._fields(doc, ['editable_price_list_rate'])
        doc.set('editable_price_list_rate', 0)
        return self._save(doc)

    def create_price_list(self, name, currency):
        """Create a selling-only list; duplicate handling remains engine-owned."""
        self._doc('Currency', currency)
        # Native creation can set the default list; require permission for that setting too.
        settings = self._doc('Selling Settings', 'Selling Settings', 'write')
        self._fields(settings, ['selling_price_list'])
        return self._create('Price List', dict(price_list_name=_text(name), currency=currency,
                                               selling=1, buying=0, enabled=1))

    def create_item_price(self, price_list, item, uom, rate):
        """Create one explicit list price; engine hooks validate UOM and duplicate ranges."""
        rate = _number(rate)
        price = self._price_list(price_list)
        self._doc('Item', item)
        self._doc('UOM', uom)
        return self._create('Item Price', dict(price_list=price_list, item_code=item, uom=uom,
                                               currency=price.get('currency'), price_list_rate=rate))

    def create_volume_discount(self, title, company, price_list, item, min_qty, discount):
        """Create a company/item/list scoped quantity discount with no executable condition."""
        min_qty, discount = _number(min_qty), _number(discount, percent=True)
        if Decimal(discount) >= 100:
            raise TradingError('TRD-NUMBER', reason='outside_allowed_range')
        company_doc = self._doc('Company', company)
        price = self._price_list(price_list)
        self._doc('Item', item)
        if price.get('currency') != company_doc.get('default_currency'):
            raise TradingError('TRD-CURRENCY')
        return self._create('Pricing Rule', dict(
            title=_text(title), company=company, currency=price.get('currency'),
            for_price_list=price_list, apply_on='Item Code', items=[{'item_code': item}],
            selling=1, buying=0, price_or_product_discount='Price',
            rate_or_discount='Discount Percentage', min_qty=min_qty, discount_percentage=discount),
            children=(('Pricing Rule Item Code', ('item_code',)),))

    def set_credit_limit(self, customer, company, limit):
        """Upsert one company limit, retaining other companies and clearing the bypass.

        Zero is refused: native zero can mean unlimited rather than a credit hold.
        A credit-management session role is required in addition to native permissions.
        Human approval binding remains a host activation gate (ERP-023 / ERP-008).
        Existing Accounts Settings.credit_controller exemptions remain untouched.
        Native submission hooks alone enforce exposure and receivable calculations.
        """
        self._require_credit_role()
        limit = _number(limit)
        self._doc('Company', company)
        doc = self._doc('Customer', customer, 'write')
        self._fields(doc, ['credit_limits'])
        self._fields(doc, ['company', 'credit_limit', 'bypass_credit_limit_check'],
                     doctype='Customer Credit Limit')
        matches = [r for r in doc.get('credit_limits') or [] if r.get('company') == company]
        if len(matches) > 1:
            raise TradingError('TRD-CREDIT')
        values = dict(company=company, credit_limit=limit, bypass_credit_limit_check=0)
        if matches:
            matches[0].update(values)
        else:
            doc.append('credit_limits', values)
        return self._save(doc)

    def _rep(self, name, action='read'):
        doc = self._doc('Sales Person', name, action)
        self._fields(doc, ['commission_rate'], write=(action == 'write'))
        if doc.get('is_group') != 0 or doc.get('enabled') != 1:
            raise TradingError('TRD-REP')
        return doc

    def set_commission_rate(self, sales_person, rate):
        """Set a master percentage for future attribution; never post or settle a commission."""
        rate = _number(rate, percent=True, zero=True)
        doc = self._rep(sales_person, 'write')
        doc.set('commission_rate', rate)
        return self._save(doc)

    def set_sales_team(self, order, allocations):
        """Replace attribution on a draft order using current, permission-checked master rates.

        Inputs contain only rep names and shares. Native save computes the informational
        allocated amounts/incentives. No accrued liability, payment or payroll is created.
        """
        doc = self._doc('Sales Order', order, 'write')
        self._fields(doc, ['sales_team'])
        self._fields(doc, ['sales_person', 'allocated_percentage', 'commission_rate'],
                     doctype='Sales Team')
        if doc.get('docstatus') != 0:
            raise TradingError('TRD-DRAFT')
        self._doc('Company', doc.get('company'))
        if not isinstance(allocations, list) or not 1 <= len(allocations) <= 100:
            raise TradingError('TRD-TEAM')
        team, seen, total = [], set(), Decimal(0)
        for row in allocations:
            if not isinstance(row, dict) or set(row) != {'sales_person', 'allocated_percentage'}:
                raise TradingError('TRD-TEAM')
            name = _text(row['sales_person'])
            share = _number(row['allocated_percentage'], percent=True)
            if name in seen:
                raise TradingError('TRD-TEAM')
            seen.add(name)
            rep = self._rep(name)
            rate = _number(rep.get('commission_rate'), percent=True, zero=True)
            team.append(dict(sales_person=name, allocated_percentage=share, commission_rate=rate))
            total += Decimal(share)  # Share validation only; the engine calculates every amount.
        if total != 100:
            raise TradingError('TRD-TEAM')
        doc.set('sales_team', team)
        return self._save(doc)
