# Google API Limited Use disclosure

**Draft. Last updated: 13 August 2026.**  
Publish at `[SITE_URL]/limited-use` and link it from the homepage and
[Privacy policy](privacy-policy.md). Required for Gmail **sensitive** scopes.

**App name:** Tagsmith  
**Operator:** `[LEGAL_NAME]`  
**Scopes:** `gmail.modify`, `gmail.labels` (plus OpenID email/profile for sign-in)  
**We do not use** `https://mail.google.com/`.

Tagsmith’s use and transfer to any other app of information received from
Google APIs will adhere to the
[Google API Services User Data Policy](https://developers.google.com/terms/api-services-user-data-policy),
including the Limited Use requirements.

## Limited Use commitments

1. **User-facing features only.** Gmail data is used solely to classify
   **your** messages and apply/remove Tagsmith labels (`AI/…`) and to show
   **your** review queues in the Tagsmith website.
2. **No ads.** We do not use Gmail data for advertising, including
   personalized or retargeted ads.
3. **No sale.** We do not sell Gmail data.
4. **No shared training.** We do not use Gmail data to train a generalized
   / shared ML or AI model. Per-account few-shot examples (RAG) stay
   **inside your tenant** and are deleted when you delete the account.
5. **Transfers.** We transfer Gmail-derived data only to processors needed
   to run Tagsmith (hosting, LLM classify, email delivery of transactional
   mail if any), under contracts. See [Sub-processors](sub-processors.md).
6. **Human access.** Humans access Gmail data only with your permission for
   support, for security/abuse, or as required by law — not to read mail
   for curiosity or marketing.
7. **Deletion.** You can disconnect Google and request deletion. We delete
   tokens and Gmail-derived stored data as described in the
   [Privacy policy](privacy-policy.md).
8. **Narrow scopes.** We request only `gmail.modify` and `gmail.labels`,
   not full-mail restricted scopes.

## What we do in Gmail

- Read message metadata and a **truncated, redacted** body to classify
- Create labels under a parent such as `AI/`
- Apply one primary Tagsmith label per message we handle
- **Never** mark messages read
- **Never** archive or remove `INBOX`

## Demo / verification

A video of the consent screen and this labeling behavior will be published
for Google’s OAuth verification (YouTube URL to add: `[VERIFICATION_VIDEO_URL]`).
