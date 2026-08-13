# Privacy policy

**Draft. Last updated: 13 August 2026.**  
**Not legal advice.** Review with counsel before publishing.

**Operator:** `[LEGAL_NAME]`, an individual / sole proprietor based in India,
offering the hosted service **Tagsmith** at `[SITE_URL]`.  
**Contact:** `[PRIVACY_EMAIL]` · **Post:** `[POSTAL_ADDRESS]`

This notice is standalone (not only inside the Terms). Connecting Gmail is
**not** consent to marketing email.

## 1. Who we are and what Tagsmith does

Tagsmith is a hosted mailbox assistant. After you sign in with Google, we
classify unread mail and apply labels under a parent such as `AI/` (for
example `AI/payment-sent`). We do **not** mark messages read, do **not**
archive or remove `INBOX`, and do **not** send mail as you.

The customer product is the **website only**. We do not ask you to install
software or bring your own API keys.

## 2. Google user data (Gmail) — read this section

This section is for Google API Services User Data Policy and **Limited Use**.
See also [Google Limited Use](google-limited-use.md).

### 2.1 Scopes we request

- `https://www.googleapis.com/auth/gmail.modify` (read messages we need to
  classify; apply/remove **our** labels)
- `https://www.googleapis.com/auth/gmail.labels` (create the `AI/…` labels)
- Sign-in: OpenID, email, profile (account identity)

We do **not** request `https://mail.google.com/` (restricted/full mailbox
protocol access).

### 2.2 How we access Gmail data

Using Google OAuth, our servers call the Gmail API for **your** account only.
We fetch unread (or history-changed) messages to classify them.

### 2.3 What we send to a language model

If a message is not handled by local rules, we send a **truncated, redacted**
payload to our LLM processor (`[LLM_PROCESSOR]`):

- From, To, Subject, Date
- List-Unsubscribe if present
- Attachment **filenames** (never file bytes)
- Body text capped at about **2000 characters**
- Digit runs of length **9 or more** replaced with `[REDACTED]`

We do not send raw MIME, full HTML, or attachment contents.

### 2.4 How we use Gmail data

**Only** to provide Tagsmith features you can see: classify, apply `AI/…`
labels, show review queues (held / needs review / proposals), improve
**your** few-shot examples (RAG) **inside your account**.

We do **not**:

- sell Google user data
- use it for advertising
- use it to train a **shared** or public model
- transfer it except to processors needed to run the service (below)
- let humans read your mail except as in §7

### 2.5 What we store

| Data | Retention |
|------|-----------|
| Encrypted Google refresh token | Until you disconnect or delete your account |
| Google account email, name, picture (if provided) | Until account delete |
| Message id, chosen label, confidence, short rationale | 30–90 days, or until you delete |
| Subject / sender (minimized) | Same as audit |
| Body / review excerpt | **7–14 days**, then deleted |
| RAG embeddings / hashes for **your** mailbox | Until you delete; never mixed with other users |
| Full MIME / attachments | **Never** |

Server logs: technical metadata only (no message bodies), **14–30 days**.

Billing identifiers (PayPal transaction ids, your billing email): kept while
the account exists and as required for tax (often up to ~7 years in India).

### 2.6 Disconnect and deletion

In the product: **Disconnect Google** and **Delete my data**. That revokes
tokens, deletes Gmail-derived rows (classifications, excerpts, RAG, tokens)
for your account. Labels already sitting in Gmail stay until you remove the
`AI` parent in Gmail — we cannot unsay a label that is already on a message
without a further API call; disconnect stops new labeling.

You can also revoke Tagsmith in your Google Account permissions.

## 3. Other personal data we collect

- Account identity from Google sign-in
- Plan, payment status, invoices (via `[PAYMENTS_PROCESSOR]`)
- Approximate usage (e.g. classified-per-day) for plan limits
- Support emails you send to `[SUPPORT_EMAIL]`

We do not require a separate password. We do not store card numbers (PayPal
does).

## 4. Legal bases (GDPR / UK GDPR, if you are in the EEA/UK)

- **Contract:** providing labeling after you create an account and connect
  Gmail
- **Legitimate interests:** security, fraud, keeping the service running
  (balanced against your rights)
- **Legal obligation:** tax and accounting records

Connecting Gmail is permission to Google and is how we access the API; it is
not a blanket marketing consent.

## 5. India (DPDP)

We process digital personal data in India as a **Data Fiduciary** for this
service. You may request access, correction, erasure, and grievance handling
via `[PRIVACY_EMAIL]`. We will not make Gmail connect a condition of unrelated
processing (for example marketing).

## 6. California (CCPA/CPRA)

We do **not sell** or **share** personal information for cross-context
behavioral advertising. Email contents are used **only** to provide the
service. You may request know/delete via `[PRIVACY_EMAIL]`.

## 7. Human access

People at Tagsmith may access Gmail-derived data only:

- to fix a security incident or abuse
- to debug a problem **you** asked us to look at
- where required by law

Access is limited, logged, and not used for ads.

## 8. Processors (sub-processors)

We use vendors listed on [Sub-processors](sub-processors.md). Typical
categories: Google (sign-in + Gmail API), `[LLM_PROCESSOR]`,
`[HOSTING_PROCESSOR]`, `[PAYMENTS_PROCESSOR]`.

LLM vendors must be contracted for **zero retention / no training** on API
data. If a vendor trains on your prompts, we will not use them for classify.

If an LLM or host is in the US (or another country), data may be processed
there. For EEA/UK users we rely on the vendor’s appropriate transfer
mechanism (e.g. SCCs) as described in the [DPA](dpa.md).

We do not transfer Gmail data to countries on an Indian government **negative
list** if one applies to that transfer.

## 9. Cookies

See [Cookie notice](cookie-notice.md). We use a session cookie to keep you
signed in. We do not use advertising cookies.

## 10. Children

Tagsmith is not for anyone under 18. We do not knowingly connect Gmail for
children.

## 11. Security

HTTPS; encrypted tokens at rest; tenant isolation so one customer’s examples
are not used for another; access controls. No method is perfect. See Terms
for limitation of liability.

## 12. Incidents

If a personal data breach affects you, we will notify you and (where
required) the Indian Data Protection Board and, for EEA/UK users, follow
GDPR timelines (including 72-hour supervisory notice where applicable).

## 13. Your rights

Depending on where you live, you may request: access, correction, erasure,
export of **labels we applied and dates** (not a full dump of your mailbox),
restriction, objection, and withdrawal of Google access.

We will not honor a request in a way that breaks the law (e.g. we may keep
invoices).

## 14. Changes

We will post a new date on this page. Material changes to Gmail data use
will be highlighted. Continued use after the date means you accept the
updated notice, except where the law requires a new consent.

## 15. Grievance / contact

`[PRIVACY_EMAIL]` — we aim to respond within 30 days (sooner if the law
requires).
