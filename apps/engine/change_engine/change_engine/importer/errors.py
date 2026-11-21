"""Importer domain messages; Arabic terminology awaits ADR-0033 native review."""
MESSAGES = {
    "IMP-SCHEMA": ("Invalid import schema or field mapping.", "مخطط الاستيراد أو ربط الحقول غير صالح."),
    "IMP-NUMBER": ("Invalid exact amount or quantity.", "المبلغ الدقيق أو الكمية غير صالحين."),
    "IMP-PRECISION": ("An amount exceeds the currency precision.", "يتجاوز المبلغ الدقة العشرية للعملة."),
    "IMP-LIMIT": ("Import size limit exceeded.", "تم تجاوز حد حجم الاستيراد."),
    "IMP-FORMULA": ("Spreadsheet formula content is blocked.", "تم حظر محتوى صيغ جدول البيانات."),
    "IMP-DUPLICATE": ("Duplicate business key requires review.", "يتطلب مفتاح العمل المكرر مراجعة."),
    "IMP-REPORT": ("Prevalidation is missing, stale or requires owner review.", "التحقق المسبق مفقود أو قديم أو يتطلب مراجعة المالك."),
    "IMP-BALANCE": ("Opening debits and credits do not balance exactly.", "الأرصدة الافتتاحية المدينة والدائنة غير متوازنة بدقة."),
    "IMP-RECONCILE": ("Opening detail does not reconcile to its control account.", "تفاصيل الأرصدة الافتتاحية لا تتطابق مع حساب المراقبة."),
    "IMP-AUTH": ("An authorised human session is required for this company.", "تلزم جلسة بشرية مخولة لهذه الشركة."),
    "IMP-CONFIRM": ("Confirm the exact preview using your authenticated identity.", "أكد المعاينة الدقيقة باستخدام هويتك الموثقة."),
    "IMP-CONFLICT": ("Batch identity already belongs to a different plan.", "هوية الدفعة مرتبطة بخطة مختلفة بالفعل."),
    "IMP-OPENING-CONFLICT": ("Opening balances already exist for this company.", "توجد أرصدة افتتاحية لهذه الشركة بالفعل."),
    "IMP-REFERENCE": ("Unknown or inconsistent master reference.", "مرجع البيانات الأساسية غير معروف أو غير متسق."),
    "IMP-WRITE": ("Import failed; its transaction was rolled back.", "فشل الاستيراد وتم التراجع عن معاملته."),
    "IMP-RECOVERY": ("Import outcome requires operator recovery before retry.", "تتطلب نتيجة الاستيراد معالجة المشغل قبل إعادة المحاولة."),
}


class ImportFailure(Exception):
    """Safe bilingual failure: never embed source cells or backend exceptions."""

    def __init__(self, code: str, *, report_counts: dict | None = None):
        self.code = code if code in MESSAGES else "IMP-WRITE"
        self.report_counts = report_counts
        super().__init__(self.code)

    def to_dict(self) -> dict:
        """Return catalog messages and the explicit unreviewed-Arabic marker."""
        en, ar = MESSAGES[self.code]
        result = {"code": self.code, "messages": {"en": en, "ar": ar},
                "ar_review": "unreviewed_arabic"}
        if self.report_counts is not None:
            result["report_counts"] = self.report_counts
        return result
