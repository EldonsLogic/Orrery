"""Fictional name pools and per-market configuration. Everything here is invented; see README (fake identifiers)."""
from __future__ import annotations

# (arabic, english) stems. Invented; a chance match with a real firm is possible and harmless.
STEMS = [
    ("النخيل", "Al Nakheel"), ("الأفق", "Al Ufuq"), ("السنابل", "Al Sanabel"), ("الربيع", "Al Rabee"),
    ("المنارة", "Al Manara"), ("الشروق", "Al Shorouk"), ("الندى", "Al Nada"), ("الغدير", "Al Ghadeer"),
    ("الينابيع", "Al Yanabee"), ("الفجر", "Al Fajr"), ("البيدر", "Al Baidar"), ("السهم", "Al Sahm"),
    ("الجداول", "Al Jadawel"), ("الرحاب", "Al Rihab"), ("الأمواج", "Al Amwaj"), ("الخيمة", "Al Khaima"),
    ("الصفاء", "Al Safa"), ("الغصن", "Al Ghusn"), ("الميناء", "Al Mina"), ("السحاب", "Al Sahab"),
]
ACTIVITIES = [
    ("للتجارة العامة", "General Trading"), ("للتوزيع", "Distribution"), ("للمواد الغذائية", "Foodstuff Trading"),
    ("للتموين", "Catering Supplies"), ("للمستلزمات المكتبية", "Office Supplies"), ("للتغليف", "Packaging"),
    ("للمنظفات", "Cleaning Supplies"), ("للمشروبات", "Beverage Trading"),
]
# Items: code, ar, en, group, unit, base cost, base price (in the market-neutral base scale, see MARKETS[..]["scale"]).
ITEMS = [
    ("ITEM-001", "دفتر ملاحظات A5", "Notebook A5", "stationery", "piece", "10.00", "15.00"),
    ("ITEM-002", "أرز حبة طويلة 10 كجم", "Long grain rice 10 kg", "food_dry", "carton", "85.00", "110.00"),
    ("ITEM-003", "سكر أبيض 1 كجم", "White sugar 1 kg", "food_dry", "carton", "38.00", "49.00"),
    ("ITEM-004", "مياه معبأة 330 مل", "Bottled water 330 ml", "beverages", "carton", "12.00", "18.00"),
    ("ITEM-005", "عصير برتقال 1 لتر", "Orange juice 1 L", "beverages", "carton", "40.50", "55.00"),
    ("ITEM-006", "سائل غسيل الأطباق 750 مل", "Dish soap 750 ml", "cleaning", "carton", "52.00", "70.00"),
    ("ITEM-007", "منظف أرضيات 4 لتر", "Floor cleaner 4 L", "cleaning", "carton", "60.00", "82.00"),
    ("ITEM-008", "كرتون تغليف متوسط", "Corrugated box M", "packaging", "piece", "1.80", "2.75"),
    ("ITEM-009", "رول غلاف شد", "Stretch film roll", "packaging", "piece", "14.00", "21.50"),
    ("ITEM-010", "أقلام حبر أزرق", "Ballpoint pens blue", "stationery", "carton", "18.00", "27.00"),
    ("ITEM-011", "عدس أحمر", "Red lentils", "food_dry", "kg", "4.20", "6.10"),
    ("ITEM-012", "طبلية ورق تصوير", "Copy paper pallet", "stationery", "pallet", "900.00", "1250.00"),
    ("ITEM-013", "صنف تجريبي للتقريب", "Rounding probe item", "stationery", "piece", "1.00", None),
]
ITEM_GROUPS = [
    ("food_dry", "مواد غذائية جافة", "Dry food"), ("beverages", "مشروبات", "Beverages"),
    ("cleaning", "منظفات", "Cleaning"), ("packaging", "تغليف", "Packaging"),
    ("stationery", "قرطاسية", "Stationery"),
]
UNITS = [("piece", "قطعة", "Piece"), ("carton", "كرتونة", "Carton"), ("kg", "كيلوغرام", "Kilogram"),
         ("pallet", "طبلية", "Pallet")]
ROLES = [  # ids from the BPL-005 trading and distribution Blueprint fixture
    ("owner", "المالك", "Owner"), ("general_manager", "المدير العام", "General manager"),
    ("accountant", "المحاسب", "Accountant"), ("sales_rep", "مندوب مبيعات", "Sales representative"),
    ("branch_sales_manager", "مدير مبيعات الفرع", "Branch sales manager"),
    ("purchasing_officer", "مسؤول المشتريات", "Purchasing officer"),
    ("warehouse_keeper", "أمين المستودع", "Warehouse keeper"), ("auditor", "المدقق", "Auditor"),
]
USER_NAMES = [  # invented given names with a "Sample" family name
    ("سامي", "Sami"), ("ليلى", "Layla"), ("هدى", "Huda"), ("ماجد", "Majed"), ("رنا", "Rana"),
    ("طارق", "Tarek"), ("دانة", "Dana"), ("يوسف", "Yousef"),
]

MARKETS = {
    "SA": {
        "file": "ksa.json", "country_ar": "المملكة العربية السعودية", "country_en": "Saudi Arabia",
        "currency": "SAR", "tz": "Asia/Riyadh", "cc": "966", "vat_rate": "15", "scale": "1", "probe": "37.50",
        "legal_ar": "شركة {}", "legal_en": "{} Co.", "cities": [("الرياض", "Riyadh"), ("جدة", "Jeddah"), ("الدمام", "Dammam")],
        "tenant": ("شركة الواحة للتوزيع التجاري", "Al Waha Distribution Trading Co.", "الواحة", "Al Waha", "al-waha"),
        "individual": ("سالم التجريبي", "Salem Sample"),
    },
    "AE": {
        "file": "uae.json", "country_ar": "الإمارات العربية المتحدة", "country_en": "United Arab Emirates",
        "currency": "AED", "tz": "Asia/Dubai", "cc": "971", "vat_rate": "5", "scale": "1", "probe": "10.10",
        "legal_ar": "{} ذ.م.م", "legal_en": "{} LLC", "cities": [("دبي", "Dubai"), ("أبوظبي", "Abu Dhabi"), ("الشارقة", "Sharjah")],
        "tenant": None, "individual": ("خالد التجريبي", "Khalid Sample"),
    },
    "EG": {
        "file": "egy.json", "country_ar": "جمهورية مصر العربية", "country_en": "Egypt",
        "currency": "EGP", "tz": "Africa/Cairo", "cc": "20", "vat_rate": "14", "scale": "12", "probe": "8.25",
        "legal_ar": "شركة {} ش.م.م", "legal_en": "{} S.A.E.", "cities": [("القاهرة", "Cairo"), ("الإسكندرية", "Alexandria"), ("الجيزة", "Giza")],
        "tenant": None, "individual": ("محمود التجريبي", "Mahmoud Sample"),
    },
    "QA": {
        "file": "qat.json", "country_ar": "دولة قطر", "country_en": "Qatar",
        "currency": "QAR", "tz": "Asia/Qatar", "cc": "974", "vat_rate": "0", "scale": "1", "probe": "37.50",
        "legal_ar": "{} ذ.م.م", "legal_en": "{} W.L.L.", "cities": [("الدوحة", "Doha"), ("الريان", "Al Rayyan"), ("الوكرة", "Al Wakrah")],
        "tenant": None, "individual": ("ناصر التجريبي", "Nasser Sample"),
    },
}
