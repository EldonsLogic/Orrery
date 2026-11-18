# Interview protocol v0 (Arabic and English)

Status: draft
Owner: eldon
Plan ID: DSC-001. The interviews themselves are GTM-002; the synthesis is GTM-003.

This is the script and rulebook interviewers use for the 25-interview plan in [../gtm/README.md](../gtm/README.md). Personas ([personas.md](personas.md)) and the niche ([../strategy/02-niche-and-launch-country.md](../strategy/02-niche-and-launch-country.md)) are hypotheses until these interviews test them. Evidence on how owner-led firms buy is thin (UNVERIFIED, [../research/02-market-and-customer.md](../research/02-market-and-customer.md) section 2).

**Arabic status.** Every Arabic string in this file is `unreviewed` (ADR-0033): written by a model, not yet read by a native Arabic speaker. Do not use a string with a participant until a native speaker has reviewed it; until then interview in English or in the interviewer's own words. Each Arabic cell ends with the tag `(unreviewed)` so the status survives copy and paste. Style: Modern Standard Arabic, Gulf-friendly, addressing the participant as أنت, no heavy dialect ([../brand/06-voice-tone.md](../brand/06-voice-tone.md)). Dialect notes are in section 9.

## 1. Purpose and what we must learn
We are testing whether a chat-built ERP for owner-led firms (10-100 staff) in the Middle East solves a pain people already pay to fix. We are not selling. Ten learning goals, each with the question IDs that cover it (section 5):

| # | We must learn | Why it matters | Question IDs |
|---|---|---|---|
| L1 | ICP: size, sector, country, branches, who the buyer is | Confirms or kills the trading and distribution niche | A1-A5 |
| L2 | Pains in the current way of working, in their words | Kill criterion: 8 of 25 describe a pain they would pay to fix | B1-B6 |
| L3 | Who decides, who influences, who vetoes (owner, accountant, partner) | Kill criterion: accountant veto in more than half | C1-C5 |
| L4 | Willingness to pay: price range, setup fee, how they pay for software today | Kill criterion: fewer than 5 would pay SAR 2K or more a month | D1-D6 |
| L5 | Current tools and spend (Excel, WhatsApp, accounting app, Odoo, other) | Connectors, migration, competitor map | E1-E5 |
| L6 | Month-end process: who, how long, where it breaks | Shapes the simulated-month promise and reports | F1-F5 |
| L7 | VAT and e-invoicing habits and status per country | Compliance profile, ZATCA wave, UAE e-invoicing readiness | G1-G5 |
| L8 | Payroll and WPS handling | Scope of the later HR release | H1-H3 |
| L9 | Approvals: discounts, payments, credit, purchase orders | Blueprint approvals and thresholds | I1-I4 |
| L10 | Trust in AI for books, data and hosting worries, language preference | Positioning, human-gate messaging, Arabic priority | J1-J6 |

Kill criteria and the mix (about 15 owners or GMs, 7 accountants or VAT consultants, 3 implementers) come from [../gtm/README.md](../gtm/README.md); do not change them here.

## 2. Consent, recording and data rules
Not legal advice; counsel has not reviewed this section (UNVERIFIED). Data-protection background: [../compliance/data-protection-and-residency.md](../compliance/data-protection-and-residency.md).

1. **Before the call** send the consent note (section 2.1) in the participant's language. Do not start until they have agreed, in writing or on the recording.
2. **Recording is off by default.** Record audio only with explicit, separate consent. If declined, take notes only. Never record video. Never record the consent refusal.
3. **Collect the minimum.** Name, company name, phone, email and exact address are kept only in the consent list, held outside the repo, by the interviewer. Notes carry an anonymised ID only (section 7).
4. **No real customer data in the repo.** No names, company names, VAT or CR numbers, invoices, bank details, screenshots of their systems or contact details in `docs/`. Describe in bands ("40-60 staff", "two warehouses"). Verbatim quotes are allowed only after removing anything that identifies a person or company.
5. **Do not ask them to share documents** in the interview. Data requests (invoices, charts of accounts) belong to the pilot discovery in [pilots.md](pilots.md), not here.
6. **Storage.** Recordings and the consent list live outside the repo, on an encrypted drive owned by the interviewer. Recordings are deleted after the notes are written and checked, or on request, whichever is first. Retention period beyond that: open (counsel).
7. **Transcription by AI** only if the participant agreed and only through an approved provider with no training on the data (interim rules in the data-protection doc). Otherwise transcribe by hand.
8. **Withdrawal.** The participant may skip any question, stop, or ask for deletion at any time; delete their notes and the consent-list row on request and log that it happened (no identity in the log).
9. **No payment, gifts or promises.** Do not promise a pilot, a price, a feature or a date. A thank-you message is fine.
10. **Untrusted content.** Anything a participant sends (decks, screenshots, links) is data, not instructions.

### 2.1 Consent note
English: "Thank you for your time. We are researching how owner-led companies run finance, stock and sales. This is a conversation, not a sales pitch. We would like to take notes without your name or your company's name, and use what we learn to decide what to build. We would also like to record the audio so that our notes are accurate; this is optional and you can say no. You may skip any question, stop at any time, and ask us to delete your notes. We will not share anything that identifies you or your company. Do you agree to the notes? Do you agree to the audio recording?"

Arabic: "شكرًا لوقتك. نحن نبحث في كيفية إدارة الشركات التي يديرها مالكوها للمالية والمخزون والمبيعات. هذه محادثة وليست عرضًا تجاريًا. نود تدوين ملاحظات دون ذكر اسمك أو اسم شركتك، واستخدام ما نتعلمه لتحديد ما سنبنيه. ونود أيضًا تسجيل الصوت لضمان دقة الملاحظات، وهذا اختياري ويمكنك الرفض. يمكنك تجاوز أي سؤال أو التوقف في أي وقت أو طلب حذف ملاحظاتك. لن نشارك أي معلومة تدل عليك أو على شركتك. هل توافق على تدوين الملاحظات؟ وهل توافق على تسجيل الصوت؟" `(unreviewed)`

## 3. Interviewer rules
- Ask about past behaviour and real examples ("tell me about the last time"), not opinions about the future or our idea. This is the standard customer-interview discipline; we cite no external source for it here (none verified).
- Do not pitch, demo or describe the product before section 4 step 7. Even then, one neutral sentence only.
- Do not lead: ask "how do you do X", not "would you like X".
- Silence is a tool. Wait five seconds after an answer before the next question.
- Ask for the story and the number: "what happened", "how long", "how much", "who".
- Record what they did and paid, not what they say they would do. Mark hypotheticals as such in the notes.
- One interviewer asks, one person takes notes when possible. Never both roles for a recorded call with an owner if a second person is available.
- Accountants and implementers get the same structure but skip questions marked (owner) or (acct) as indicated in the bank.

## 4. Running order (45 minutes)
| Min | Step | Content | Notes |
|---|---|---|---|
| 0-3 | 1. Open and consent | Thank, purpose, consent note (2.1), recording choice, language choice | Offer Arabic or English first; follow the participant's language |
| 3-8 | 2. Context | A1-A5: who they are, size, sector, country, role | Fill the anonymised header (section 7) |
| 8-16 | 3. Current way of working | E1-E5 tools and spend; F1-F5 month-end | Ask for the last month, step by step |
| 16-24 | 4. Pains | B1-B6; the last time something went wrong | Probe cost, time, risk, who was blamed |
| 24-30 | 5. Compliance, payroll, approvals | G1-G5, H1-H3, I1-I4 (skip rows that do not fit the role) | Mark status as stated, never verify on the call |
| 30-35 | 6. Buying | C1-C5 decision and veto; D1-D2 last purchase and spend | The last real purchase, not a hypothetical |
| 35-41 | 7. Concept reaction and price | One neutral sentence (below), then J1-J6 trust, then D3-D6 price ladder | Price questions come last so they do not bias earlier answers |
| 41-45 | 8. Close | "What did I not ask that I should have?" and "Who else should we talk to?" (K1-K2); thank; restate deletion rights | Referral ask is optional, never required |

Neutral concept sentence (one only): "Imagine describing your company in a chat, and getting a working finance, stock and sales system that a team reviews before it goes live." Arabic: "تخيّل أنك تصف شركتك في محادثة، ثم تحصل على نظام يعمل للمالية والمخزون والمبيعات يراجعه فريق قبل التشغيل." `(unreviewed)`

If time runs short, keep in this order: B, C, D1-D2, F, G, then the rest. If the participant is an accountant, spend more time on C, F, G and I; if an implementer, on E, C and D.

## 5. Question bank
Role marks: (owner), (acct) accountant or VAT consultant, (impl) implementer; unmarked means all. IDs are `IQ-` internally; they are not open-question numbers. The Arabic column is `unreviewed` throughout.

### A. Context (L1)
| ID | English | Arabic (unreviewed) |
|---|---|---|
| A1 | Tell me about the company in a few sentences: what it sells and to whom. | حدّثني عن الشركة في بضع جمل: ماذا تبيع ولمن؟ `(unreviewed)` |
| A2 | Roughly how many people work there, and how many branches or warehouses? | كم عدد العاملين تقريبًا، وكم عدد الفروع أو المستودعات؟ `(unreviewed)` |
| A3 | Which countries do you operate and invoice in? | في أي دول تعملون وتُصدرون فواتيركم؟ `(unreviewed)` |
| A4 | What is your role, and who else touches the finance and stock work? | ما دورك، ومن غيرك يعمل على المالية والمخزون؟ `(unreviewed)` |
| A5 | How long has the company been running, and has the way you work changed recently? | منذ متى تعمل الشركة، وهل تغيّرت طريقة عملكم مؤخرًا؟ `(unreviewed)` |

### B. Pains (L2)
| ID | English | Arabic (unreviewed) |
|---|---|---|
| B1 | What is the most frustrating part of running sales, stock and finance today? | ما أكثر ما يزعجك في إدارة المبيعات والمخزون والمالية حاليًا؟ `(unreviewed)` |
| B2 | Tell me about the last time something went wrong: an invoice, a stock count, a payment. What happened? | احكِ لي عن آخر مرة حدث فيها خطأ: فاتورة أو جرد أو دفعة. ماذا حدث؟ `(unreviewed)` |
| B3 | What did it cost you, in time or money? | كم كلّفك ذلك من وقت أو مال؟ `(unreviewed)` |
| B4 | What have you already tried to fix it? | ماذا جرّبتم لحل هذه المشكلة؟ `(unreviewed)` |
| B5 | If you could change one thing about how you track what customers owe you, what would it be? | لو استطعت تغيير شيء واحد في متابعة المبالغ المستحقة على العملاء، فما هو؟ `(unreviewed)` |
| B6 | Is there a problem you live with because fixing it looks too hard or too expensive? | هل هناك مشكلة تتعايشون معها لأن حلّها يبدو صعبًا أو مكلفًا؟ `(unreviewed)` |

### C. Decision, influence, veto (L3)
| ID | English | Arabic (unreviewed) |
|---|---|---|
| C1 | Think of the last software you bought or changed. Who first suggested it? | فكّر في آخر برنامج اشتريتموه أو غيّرتموه. من اقترحه أولًا؟ `(unreviewed)` |
| C2 | Who made the final decision, and who could have stopped it? | من اتخذ القرار النهائي، ومن كان بإمكانه إيقافه؟ `(unreviewed)` |
| C3 | What role does your external accountant or VAT consultant play in choosing software? | ما دور المحاسب الخارجي أو مستشار الضريبة في اختيار البرامج؟ `(unreviewed)` |
| C4 (acct) | When a client wants to change their accounting tool, what do you ask for, and what makes you say no? | حين يريد عميل تغيير برنامجه المحاسبي، ماذا تطلب، وما الذي يجعلك ترفض؟ `(unreviewed)` |
| C5 (impl) | How do customers find you, and what do they ask you for that no product gives them? | كيف يصل إليك العملاء، وماذا يطلبون منك ولا يوفره أي منتج؟ `(unreviewed)` |

### D. Spend and willingness to pay (L4)
| ID | English | Arabic (unreviewed) |
|---|---|---|
| D1 | What do you pay today for accounting, ERP or invoicing tools, per month or year? Include the accountant and any partner. | كم تدفعون حاليًا مقابل برامج المحاسبة أو تخطيط الموارد أو الفواتير، شهريًا أو سنويًا؟ احسب المحاسب وأي شريك تقني. `(unreviewed)` |
| D2 | What was the last thing you paid a setup or project fee for, and how much was it? | ما آخر شيء دفعتم عنه رسوم تأسيس أو مشروع، وكم كانت؟ `(unreviewed)` |
| D3 | At what monthly price would a system like the one I described feel so cheap you doubt it works? | عند أي سعر شهري سيبدو نظام كالذي وصفته رخيصًا لدرجة أنك تشك في جودته؟ `(unreviewed)` |
| D4 | At what price would it start to feel expensive but still worth considering? | عند أي سعر يبدأ بالظهور مكلفًا لكنه ما زال يستحق النظر؟ `(unreviewed)` |
| D5 | At what price would it be too expensive to consider at all? | عند أي سعر يصبح مرتفعًا جدًا بحيث لا تنظر فيه؟ `(unreviewed)` |
| D6 | How would you feel about a one-time setup fee on top of the monthly price? What range is normal? | ما رأيك برسوم تأسيس لمرة واحدة فوق السعر الشهري؟ وما النطاق المعتاد؟ `(unreviewed)` |

D3-D5 follow the price-ladder idea in [../gtm/README.md](../gtm/README.md) (Van Westendorp-style). Do not anchor: never say a number first. Record currency and period as stated. Hypotheses to test live in [../strategy/07-pricing.md](../strategy/07-pricing.md); do not read them out.

### E. Current tools (L5)
| ID | English | Arabic (unreviewed) |
|---|---|---|
| E1 | Which tools do you use for invoices, stock, customers and accounts? Spreadsheets, chat apps, an accounting app, an ERP? | ما الأدوات التي تستخدمونها للفواتير والمخزون والعملاء والحسابات؟ جداول بيانات أم تطبيقات مراسلة أم برنامج محاسبة أم نظام تخطيط موارد؟ `(unreviewed)` |
| E2 | Who set it up, and who maintains it today? | من أعدّه، ومن يتولى صيانته اليوم؟ `(unreviewed)` |
| E3 | What do you do in it, and what do you do outside it, for example in WhatsApp or Excel? | ما الذي تنجزونه داخله، وما الذي تنجزونه خارجه، مثل واتساب أو إكسل؟ `(unreviewed)` |
| E4 | If you use Odoo or another ERP: what limits you, and what must you keep if you move? | إن كنتم تستخدمون أودو أو نظامًا آخر: ما الذي يقيّدكم، وما الذي يجب أن تحتفظوا به عند الانتقال؟ `(unreviewed)` |
| E5 | Have you ever switched systems? How long did it take and what went wrong? | هل غيّرتم نظامكم من قبل؟ كم استغرق الأمر، وما الذي لم يسر كما ينبغي؟ `(unreviewed)` |

### F. Month-end (L6)
| ID | English | Arabic (unreviewed) |
|---|---|---|
| F1 | Walk me through the last month-end, from the last day of the month until the books were closed. | اشرح لي إغلاق آخر شهر خطوة بخطوة، من آخر يوم في الشهر حتى إقفال الدفاتر. `(unreviewed)` |
| F2 | Who does each step, and how many days does it take? | من ينفذ كل خطوة، وكم يومًا يستغرق؟ `(unreviewed)` |
| F3 | Where do numbers not match: stock, customer balances, supplier balances, bank? | أين لا تتطابق الأرقام: المخزون أم أرصدة العملاء أم الموردين أم البنك؟ `(unreviewed)` |
| F4 | What reports do you look at, and when do you trust them? | ما التقارير التي تطّلع عليها، ومتى تثق بها؟ `(unreviewed)` |
| F5 | What do you hand to the external accountant, in what form, and how often? | ماذا تسلّمون للمحاسب الخارجي، وبأي صيغة، وكم مرة؟ `(unreviewed)` |

### G. VAT and e-invoicing (L7)
| ID | English | Arabic (unreviewed) |
|---|---|---|
| G1 | Are you registered for VAT, and who prepares and files the return? How often? | هل أنتم مسجلون في ضريبة القيمة المضافة، ومن يعدّ الإقرار ويقدّمه؟ وكم مرة؟ `(unreviewed)` |
| G2 | How do you issue invoices today, and which system or format? | كيف تُصدرون الفواتير اليوم، وبأي نظام أو صيغة؟ `(unreviewed)` |
| G3 | What is your status with electronic invoicing in your country? What have you been told you must do, and by when? | ما وضعكم في الفوترة الإلكترونية في بلدكم؟ وماذا قيل لكم إنه مطلوب، وفي أي موعد؟ `(unreviewed)` |
| G4 | Who is helping you with that, and how much is it costing? | من يساعدكم في ذلك، وكم يكلّفكم؟ `(unreviewed)` |
| G5 | How do you handle credit notes, returns and mistakes on issued invoices? | كيف تتعاملون مع الإشعارات الدائنة والمرتجعات وأخطاء الفواتير الصادرة؟ `(unreviewed)` |

Record the status as the participant states it. Do not confirm or correct regulatory facts on the call; our own claims on ZATCA and other regimes stay UNVERIFIED until the compliance docs say otherwise ([../compliance/e-invoicing.md](../compliance/e-invoicing.md)).

### H. Payroll (L8)
| ID | English | Arabic (unreviewed) |
|---|---|---|
| H1 | How do you pay staff today, and who prepares the payroll? | كيف تدفعون رواتب الموظفين اليوم، ومن يعدّ كشف الرواتب؟ `(unreviewed)` |
| H2 | Do you use a bank payroll file or a government wage-protection system, and who submits it? | هل تستخدمون ملف رواتب للبنك أو نظام حماية الأجور الحكومي، ومن يرفعه؟ `(unreviewed)` |
| H3 | What goes wrong most often in payroll? | ما أكثر ما يخطئ في الرواتب؟ `(unreviewed)` |

### I. Approvals (L9)
| ID | English | Arabic (unreviewed) |
|---|---|---|
| I1 | Who can give a discount, and above what amount or percent do they need to ask you? | من يحق له منح خصم، وما المبلغ أو النسبة التي تتطلب الرجوع إليك؟ `(unreviewed)` |
| I2 | Who approves a purchase order or a supplier payment, and up to what amount? | من يعتمد أمر الشراء أو دفعة المورد، وإلى أي مبلغ؟ `(unreviewed)` |
| I3 | How do you decide how much credit a customer gets, and what happens when they pay late? | كيف تقررون حجم الائتمان للعميل، وماذا يحدث عند تأخره في السداد؟ `(unreviewed)` |
| I4 | How do approvals happen today: in person, by phone, by message? Show me the last one. | كيف تتم الموافقات اليوم: مباشرة أم هاتفيًا أم برسالة؟ أرني آخر واحدة. `(unreviewed)` |

### J. Trust in AI, data and language (L10)
| ID | English | Arabic (unreviewed) |
|---|---|---|
| J1 | Have you used AI tools for work? Tell me about one specific time. | هل استخدمت أدوات الذكاء الاصطناعي في العمل؟ احكِ لي عن مرة محددة. `(unreviewed)` |
| J2 | Would you let an AI prepare a draft of your accounting setup if a person reviewed it before use? What would you need to see first? | هل تسمح للذكاء الاصطناعي بإعداد مسودة لإعدادات حساباتك إذا راجعها شخص قبل الاستخدام؟ وماذا تحتاج أن ترى أولًا؟ `(unreviewed)` |
| J3 | Which tasks would you never let an AI do alone? | ما المهام التي لن تتركها للذكاء الاصطناعي وحده أبدًا؟ `(unreviewed)` |
| J4 | Where must your company data be stored, and who is allowed to see it? Any rules from banks, customers or regulators? | أين يجب أن تُخزَّن بيانات شركتك، ومن يحق له الاطلاع عليها؟ وهل هناك شروط من البنوك أو العملاء أو الجهات التنظيمية؟ `(unreviewed)` |
| J5 | What language do you and your staff use for work documents and systems? | ما اللغة التي تستخدمها أنت وموظفوك في مستندات العمل والأنظمة؟ `(unreviewed)` |
| J6 | If you could see a simulated month of your own numbers before going live, would that change how much you trust the result? Why? | لو رأيت شهرًا تجريبيًا من أرقامك قبل التشغيل، هل يغيّر ذلك ثقتك بالنتيجة؟ ولماذا؟ `(unreviewed)` |

J2 and J6 are reactions to our idea, so they are weaker evidence than past-behaviour questions; tag them `hypothetical` in the notes.

### K. Close
| ID | English | Arabic (unreviewed) |
|---|---|---|
| K1 | What did I not ask that I should have? | ما الذي لم أسألك عنه وكان ينبغي أن أسأله؟ `(unreviewed)` |
| K2 | Who else would be worth talking to? | من الأشخاص الآخرون الذين يستحق الحديث معهم؟ `(unreviewed)` |

## 6. Probes and red flags
**Probes** (use in either language; Arabic versions all `unreviewed`):
| Situation | English probe | Arabic (unreviewed) |
|---|---|---|
| Vague answer | "Can you give me the last example?" | "هل لديك آخر مثال على ذلك؟" `(unreviewed)` |
| Opinion not behaviour | "What did you actually do?" | "وماذا فعلتَ فعليًا؟" `(unreviewed)` |
| Want numbers | "Roughly how long or how much?" | "كم تقريبًا من الوقت أو المال؟" `(unreviewed)` |
| Emotion | "Why does that matter to you?" | "لماذا يهمك ذلك؟" `(unreviewed)` |
| Others involved | "Who else was part of that?" | "من شاركك في ذلك؟" `(unreviewed)` |
| Check completeness | "Anything else about that?" | "هل هناك شيء آخر بهذا الشأن؟" `(unreviewed)` |
| Compliments on idea | "Have you ever paid to solve this?" | "هل سبق أن دفعت لحل هذه المشكلة؟" `(unreviewed)` |

**Red flags** (note them; they do not end the interview):
- Polite enthusiasm with no past action, no money spent and no named person ("sounds great, send me details").
- Describes a pain but no cost, no workaround and nothing tried: low urgency.
- "My accountant handles everything" with no wish to involve the accountant: veto or blind spot, ask C3 again.
- A decision only a person not in the room can make (a relative, a group owner): record who.
- Wants a custom feature for themselves: per-client code is against our rules; note the need as a possible candidate component.
- Asks us to start immediately or to handle their regulatory deadline: do not promise; note urgency.
- Asks for access to or sends real documents, credentials or bank data: stop, decline, do not store (section 2).
- Price ladder answers that conflict with their stated spend in D1-D2: record both.
- Interviewer talked more than the participant: mark the notes low-confidence.

## 7. Note-taking template
One file per interview, stored with consent under `docs/research/interviews/` only after anonymisation (the folder needs an ADR or plan row if not yet allowed; check [../../AGENTS.md](../../AGENTS.md) "Where things live" first, otherwise keep outside the repo). Raw notes and recordings stay outside the repo.

**Anonymised ID:** `INT-<country>-<role>-<nn>`, for example `INT-SA-OWN-03`. Country is SA, AE, EG or QA. Role is OWN (owner or GM), ACC (accountant or VAT consultant), IMP (implementer). `nn` is a running number per country and role. The mapping from ID to person lives only in the consent list outside the repo.

```
ID: INT-__-___-__
Interviewer: <eldon|partner>   Note-taker: <eldon|partner|none>
Language: <ar|en|mixed>   Arabic strings used: <reviewed|unreviewed>
Consent: notes <yes/no>  audio <yes/no>  (no names here)
Participant band: role; staff band (1-9, 10-19, 20-49, 50-100, 100+); sectors (generic); branches (n); countries
Sourcing channel: <founder network|accountant referral|linkedin|trade association|other>

Per question ID: answer (verbatim quote in quotes, anonymised) | evidence type: past-behaviour / hypothetical / opinion | strength 0-2
 A1: ...
 B2: ...
 ...
Facts as stated (not verified): VAT registered y/n; e-invoicing status; tools; spend per period; price ladder D3-D5 with currency
Veto map: owner / accountant / partner / other; who can block (C2, C3)
Red flags seen: ...
Surprises: ...
Follow-ups needed: ...
Scoring (section 8): P __  U __  B __  V __  W __  Total __
Blueprint hints: pointer -> value as stated (section 9)
```

## 8. Scoring rubric
Score each interview straight after it, from the notes, on a 0-2 scale. Two people score independently when possible. Scores feed GTM-003; they do not replace reading the quotes.

| Code | Dimension | 0 | 1 | 2 |
|---|---|---|---|---|
| P | Pain | None or vague | Pain named, no cost or workaround | Pain with a recent example, a cost, and something already tried |
| U | Urgency | No deadline or trigger | A trigger exists (growth, e-invoicing wave) but no action | Deadline or active search; has spent time or money in the past 12 months |
| B | Buyer access | Participant cannot influence | Influences, does not decide | Decides, or has a named path to the decider |
| V | Veto risk | Accountant or partner clearly opposes or would be displaced | Unknown or neutral | Accountant or partner supportive, or no veto |
| W | Willingness to pay | Under the SAR 2K-a-month range or refuses | Gives a range that touches it | Names a figure at or above SAR 2K a month, or a comparable existing spend |

Total out of 10. Tallies for the kill criteria in [../gtm/README.md](../gtm/README.md):
- Pain count: interviews with P = 2 and a stated willingness to pay to fix it (target 8 of 25 or more to continue).
- Price count: interviews with W = 2 at SAR 2K or more per month (target 5 or more to continue).
- Veto count: interviews where the accountant would block (V = 0) over the interviews where an accountant is involved (more than half stops the niche).
Currency conversions for non-SAR answers: record the stated figure and currency; convert later in GTM-003 with a dated rate, not on the call. A total of 7 or more is a strong lead; 4 to 6 is a maybe; under 4 is noise. Treat all thresholds as v0 and change them only by a versioned edit of this file.

## 9. Dialect notes (Arabic, all `unreviewed`)
- Write and read Modern Standard Arabic; the interviewer may answer in the participant's dialect. Do not push dialect words into our written questions.
- Terms vary by country and are common confusions, so confirm the term the participant uses before probing: invoice (فاتورة, universal); credit note (إشعار دائن in formal use, often "مرتجع" in speech); stock (المخزون / البضاعة); warehouse (مستودع in the Gulf, مخزن in Egypt and the Levant); accountant (محاسب); VAT (ضريبة القيمة المضافة; shortened to "الضريبة" in speech); payroll (كشف الرواتب / مسيّر الرواتب, wording varies).
- Egyptian participants often prefer Egyptian speech; use their words in follow-ups and record the formal term in the notes.
- Gulf participants may mix English words (invoice, stock, VAT); accept both and record what they said.
- Hijri and Gregorian dates, weekend days (Friday and Saturday or Saturday and Sunday) and currency name differ by country; ask when it matters, do not assume ([../architecture/calendars-and-locale.md](../architecture/calendars-and-locale.md)).
- Politeness and hierarchy matter: use formal address until invited otherwise, and let the participant finish. Open the call with a short greeting in their language.
- Arabic numerals: record numbers as spoken, then normalise digits in the notes (Western or Eastern Arabic-Indic digits both appear).
- A native-speaker review (ADR-0033, Q-28) replaces the `unreviewed` tag; until then the English text is canonical.

## 10. How answers map to the Blueprint and to gate G1 evidence
Interviews do not fill a tenant's Blueprint (GTM-002 is research); they decide what the template and the discovery interviewer (DSC-005) should assume and ask. Pointers below come from `services/discovery/templates/trading-distribution/questions.json` ([../../services/discovery/README.md](../../services/discovery/README.md)). Blueprint contract: [../../contracts/README.md](../../contracts/README.md).

| Interview IDs | Blueprint area (JSON pointer) | What we use it for |
|---|---|---|
| A1, A3 | `/company/country`, `/compliance/country`, `/compliance/countryPack/id` | Country mix and pack priority |
| A2 | `/company` size band, `/locations` | Template default for branches and warehouses |
| J5 | `/company/languages`, `/meta/defaultLocale`, `/compliance/documentLanguages` | Arabic-first priority and document language default |
| C1-C3, I1-I4 | `/roles`, `/approvals`, `/workflows/0` and `/workflows/1` guards (sales order, discount, purchase order thresholds) | Default approvers and thresholds, role views |
| E1-E5 | connectors and `/entities` (customers, suppliers, items) | Which readers to build first (Excel, Odoo) |
| F1-F5 | `/reports` (ageing, stock, VAT), simulation scope | Month-end report set; what the simulated month must show |
| G1-G5 | `/compliance/vat`, `/compliance/eInvoicing` (mode, environment), `/compliance/vat/filingPeriod` | Compliance profile defaults and readiness checker content |
| G5, I3 | `/entities` credit notes, credit limits, `/approvals` credit notes | Credit-note approval and credit-limit defaults |
| H1-H3 | later HR release, no Blueprint field in v1 scope | Whether to pull payroll forward; evidence only |
| D1-D6 | not a Blueprint field; [pricing.md](pricing.md) and [../strategy/07-pricing.md](../strategy/07-pricing.md) | Price bands, setup fee |
| J2-J4, J6 | none; messaging for the human review gate, hosting rules ([../security/hosting-rules.md](../security/hosting-rules.md)) | Trust and data-residency requirements |

**Gate G1 link.** G1 ([../GATES.md](../GATES.md)) is "Spine proven" and is mostly technical. The interviews supply the market half of the G1 story and the niche decision, not a G1 exit item by themselves:
- The sourcing mix, scores (section 8) and the three kill-criteria counts are the evidence for the continue-or-change-niche decision recorded in `docs/decisions/` (GTM-003).
- G, F and I answers in the first pilot market feed the "compliance for the first pilot market" item: they tell us which country that is.
- Arabic-eval and invoice-review items in G1 are not served by these interviews; do not claim them.
- G2 (pilot-ready) needs Pilot A; an interview that ends in a pilot lead is logged as a lead only, not as G2 evidence ([pilots.md](pilots.md)).

## 11. What we deliberately do not ask
- Names, personal contact details beyond the consent list, national IDs, CR numbers, VAT numbers, bank details, salaries of named people, passwords or access to their systems.
- Their customers' or suppliers' identities, and anything covered by a confidentiality duty (especially for accountants and implementers about their clients).
- Requests for real invoices, ledgers, charts of accounts or exports: pilot discovery only ([pilots.md](pilots.md)).
- "Would you buy this?", "Would you use this?", "Do you like it?": opinion questions about our idea. We ask about past spend and behaviour instead.
- Feature wish lists ("what features do you want?") and design preferences: they bias toward software-house behaviour and per-client requests.
- A confirmation of regulatory facts or legal advice: we do not give or test any on the call.
- Competitors' pricing from NDA material or under-the-table information.
- Political, religious or family matters beyond who decides in the business.
- Sales commitments: no discounts, pilots, dates or promises.
- Our brand name: say "the platform" (the working name is not cleared, [../../AGENTS.md](../../AGENTS.md)).

## 12. Open points
- Native Arabic review of every Arabic string (ADR-0033); until then, English is canonical.
- Counsel review of consent wording and retention for each of the four markets (UNVERIFIED).
- Whether interview notes may be stored under `docs/research/interviews/` (layout rule) or stay outside the repo: decide with GTM-002.
- Egypt and Qatar wording and dialect checks need a native reviewer from each market.
