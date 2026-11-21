"""Closed table of change-by-chat refusals. Customer text comes only from here (ADR-0036). Arabic is UNREVIEWED."""
from __future__ import annotations

TABLE = {
    "change_not_change_mode": ("This is not a change request.", "هذا ليس طلب تغيير."),
    "change_no_permission": ("You may not change the configuration from chat.", "لا يمكنك تغيير الإعدادات من المحادثة."),
    "change_draft_failed": ("I could not turn that into a change. Please say exactly what to change.",
                            "لم أستطع تحويل ذلك إلى تغيير. يرجى توضيح ما تريد تغييره بالضبط."),
    "change_draft_invalid": ("I could not turn that into a safe change. Please rephrase it.",
                             "لم أستطع تحويل ذلك إلى تغيير آمن. يرجى إعادة الصياغة."),
    "change_forbidden_path": ("That part of the configuration cannot be changed from chat.",
                              "لا يمكن تغيير هذا الجزء من الإعدادات من المحادثة."),
    "change_ledger_tax": ("Ledger, tax and payroll setup cannot be changed from chat.",
                          "لا يمكن تغيير إعدادات الحسابات والضرائب والرواتب من المحادثة."),
    "change_no_effect": ("That change would not alter anything.", "هذا التغيير لن يغير أي شيء."),
    "change_invalid_blueprint": ("That change would make the configuration invalid, so it was not prepared.",
                                 "هذا التغيير سيجعل الإعدادات غير صالحة، لذلك لم يتم تجهيزه."),
    "change_base_invalid": ("The current configuration has problems; fix them before changing it from chat.",
                            "الإعدادات الحالية بها مشكلات؛ أصلحها قبل تغييرها من المحادثة."),
    "change_needs_review": ("This change needs a full review in Studio and cannot be applied from chat.",
                            "يحتاج هذا التغيير إلى مراجعة كاملة في الاستوديو ولا يمكن تطبيقه من المحادثة."),
    "change_no_pending": ("There is no change waiting for your confirmation.", "لا يوجد تغيير ينتظر تأكيدك."),
    "change_confirmation_mismatch": ("That confirmation is not for the change on screen. Ask again.",
                                     "هذا التأكيد ليس للتغيير المعروض. اطلب مرة أخرى."),
    "change_expired": ("The confirmation expired. Ask for the change again.",
                       "انتهت صلاحية التأكيد. اطلب التغيير مرة أخرى."),
    "change_replayed": ("This change was already confirmed once.", "تم تأكيد هذا التغيير من قبل."),
    "change_superseded": ("A newer change replaced this one. Check the latest preview.",
                          "حل تغيير أحدث محل هذا التغيير. راجع أحدث معاينة."),
    "change_preview_failed": ("The preview could not be shown, so nothing was prepared. Please rephrase the request.",
                              "تعذر عرض المعاينة، لذلك لم يتم تجهيز أي شيء. يرجى إعادة صياغة الطلب."),
    "change_stale": ("The configuration changed since the preview. Ask for the change again.",
                     "تغيرت الإعدادات منذ المعاينة. اطلب التغيير مرة أخرى."),
    "change_tampered": ("The prepared change no longer matches its preview, so it was not applied.",
                        "لم يعد التغيير المجهز مطابقا لمعاينته، لذلك لم يتم تطبيقه."),
    "change_apply_failed": ("The change could not be applied. Nothing was changed.",
                            "تعذر تطبيق التغيير. لم يتم تغيير أي شيء."),
    "change_outcome_unknown": ("I could not confirm whether the change was applied. Check the change history before "
                               "asking again.",
                               "لم أتمكن من التأكد مما إذا كان التغيير قد طُبق. راجع سجل التغييرات قبل أن تطلب مرة أخرى."),
    "change_unavailable": ("Changes from chat are unavailable right now.", "التغييرات من المحادثة غير متاحة الآن."),
}


class ChangeRefused(Exception):
    """A refusal with a code from TABLE. No raw text, no provider output."""

    def __init__(self, code: str):
        self.code = code if code in TABLE else "change_unavailable"
        super().__init__(self.code)

    def text(self, locale: str = "en") -> str:
        en, ar = TABLE[self.code]
        return ar if str(locale).lower().startswith("ar") else en
