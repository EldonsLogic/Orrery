// Synthetic proposal for the Blueprint review (WEB-029) until the gateway serves the DSC-009 review view (WEB-027, Q-683).
// Invented modules, gaps and prices for a sample trading company; the figures are placeholders, not a price book (Q-400).
import type { Proposal } from '../proposal';

export const fixtureProposal: Proposal = {
  modules: [
    {
      id: 'sales_trading',
      icon: 'receipt',
      status: 'approved',
      labels: { en: 'Sales and invoicing', ar: 'المبيعات والفوترة' },
      summary: { en: 'Quotes, sales orders and invoices, with approval for large orders.', ar: 'عروض الأسعار وأوامر البيع والفواتير، مع اعتماد الطلبات الكبيرة.' },
    },
    {
      id: 'stock_trading',
      icon: 'package',
      status: 'drafted',
      labels: { en: 'Stock and warehouses', ar: 'المخزون والمستودعات' },
      summary: { en: 'Items, two warehouses and stock counts, with low-stock alerts.', ar: 'الأصناف ومستودعان وجرد المخزون، مع تنبيه عند انخفاضه.' },
    },
    {
      id: 'purchasing_trading',
      icon: 'cart',
      status: 'drafted',
      labels: { en: 'Purchasing', ar: 'المشتريات' },
      summary: { en: 'Suppliers, purchase orders and goods received.', ar: 'الموردون وأوامر الشراء واستلام البضائع.' },
    },
    {
      id: 'zatca_sa',
      icon: 'file',
      status: 'drafted',
      labels: { en: 'Saudi e-invoicing', ar: 'الفوترة الإلكترونية السعودية' },
      summary: { en: 'Invoices in the format ZATCA requires, sent and stamped for you.', ar: 'فواتير بالصيغة التي تطلبها هيئة الزكاة والضريبة والجمارك، تُرسَل وتُختَم عنك.' },
    },
    {
      id: 'company_calendar',
      icon: 'settings',
      status: 'approved',
      labels: { en: 'Company calendar', ar: 'تقويم الشركة' },
      summary: { en: 'Your working week, public holidays and Ramadan hours.', ar: 'أسبوع العمل والعطل الرسمية وساعات رمضان.' },
    },
    {
      id: 'hrms_skeleton',
      icon: 'users',
      status: 'drafted',
      labels: { en: 'People', ar: 'الموظفون' },
      summary: { en: 'Staff records, job roles and who approves what.', ar: 'سجلات الموظفين والأدوار الوظيفية ومن يعتمد ماذا.' },
    },
  ],
  gaps: [
    {
      id: 'branch_statement',
      kind: 'report',
      status: 'partial',
      labels: { en: 'Customer statements by branch', ar: 'كشوف حساب العملاء حسب الفرع' },
      plan: { en: 'The standard statement covers the whole company. We add a branch filter.', ar: 'الكشف القياسي يغطي الشركة كلها. سنضيف تصفية حسب الفرع.' },
    },
    {
      id: 'delivery_routes',
      kind: 'component',
      status: 'uncovered',
      labels: { en: 'Delivery routes for your drivers', ar: 'مسارات التوصيل للسائقين' },
      plan: { en: 'We build this once as a new module for every customer. It is in the one-off charges below.', ar: 'نبنيها مرة واحدة كوحدة جديدة لكل العملاء، وهي ضمن الرسوم لمرة واحدة أدناه.' },
    },
  ],
  price: {
    currency: 'SAR',
    vatRatePercent: '15',
    monthly: {
      lines: [
        { id: 'base', labels: { en: 'Platform, unlimited users', ar: 'المنصة، مستخدمون بلا حد' }, amount: '1200.00' },
        { id: 'stock', labels: { en: 'Stock and warehouses', ar: 'المخزون والمستودعات' }, amount: '300.00' },
        { id: 'purchasing', labels: { en: 'Purchasing', ar: 'المشتريات' }, amount: '200.00' },
        { id: 'einvoice', labels: { en: 'Saudi e-invoicing', ar: 'الفوترة الإلكترونية السعودية' }, amount: '250.00' },
      ],
      subtotal: '1950.00',
      vat: '292.50',
      total: '2242.50',
    },
    oneOff: {
      lines: [
        { id: 'setup', labels: { en: 'Setup and configuration', ar: 'الإعداد والتهيئة' }, amount: '4000.00' },
        { id: 'routes', labels: { en: 'New module: delivery routes', ar: 'وحدة جديدة: مسارات التوصيل' }, amount: '6500.00' },
      ],
      subtotal: '10500.00',
      vat: '1575.00',
      total: '12075.00',
    },
  },
};
