# Power Automate — Venmo Payment Confirmation Flow

This flow monitors your Outlook inbox for Venmo payment emails and automatically
marks the matching order as **paid** in Supabase by calling `/api/mark-paid`.

---

## Prerequisites

- A **Microsoft Power Automate** account (free tier works)
- An **Office 365 Outlook** connection in Power Automate (your @outlook.com or
  work email that receives Venmo notifications)
- Your deployed app URL (e.g. `https://your-app.vercel.app`)
- Your `MARK_PAID_SECRET` value from `.env.local`

---

## How to Import

### Option A — Create from JSON (recommended)

1. Go to [make.powerautomate.com](https://make.powerautomate.com)
2. Click **+ Create** → **Instant cloud flow** (name it anything) → skip trigger
3. Click the **⋯ menu** (top right of the canvas) → **Export** → note the format
4. Instead, click **Edit in advanced mode** (the `</>` code button in the toolbar)
5. Paste the entire contents of `definition.json` into the editor
6. Click **Save**
7. Follow the **Configuration** steps below

### Option B — Build manually (5 steps)

1. **Trigger:** *Office 365 Outlook — When a new email arrives (V3)*
   - Folder: `Inbox`
   - From: `venmo@venmo.com`
   - Subject filter: `You received`
   - Check every: `2 minutes`

2. **Compose — Extract_Amount**
   - Inputs (expression):
     ```
     trim(first(split(last(split(triggerOutputs()?['body/subject'], '$')), ' ')))
     ```
   - Result for subject `"You received $25.00 from John Doe"` → `25.00`

3. **Compose — Extract_Name**
   - Inputs (expression):
     ```
     trim(last(split(triggerOutputs()?['body/subject'], ' from ')))
     ```
   - Result → `John Doe`

4. **HTTP — Call_Mark_Paid_Webhook**
   - Method: `POST`
   - URI: `https://YOUR_APP_DOMAIN/api/mark-paid`
   - Headers:
     | Key | Value |
     |-----|-------|
     | `Authorization` | `Bearer YOUR_MARK_PAID_SECRET` |
     | `Content-Type` | `application/json` |
   - Body:
     ```json
     {
       "name":   "@{outputs('Extract_Name')}",
       "amount": "@{outputs('Extract_Amount')}"
     }
     ```

5. **Condition — Check_Response**
   - Condition: `outputs('Call_Mark_Paid_Webhook')['statusCode']` **is equal to** `200`
   - **Yes branch:** Send email — subject `✅ Venmo payment confirmed — ...`
   - **No branch:** Send email (High importance) — `⚠️ Needs manual review — ...`

---

## Configuration — Required substitutions

Open `definition.json` and replace these three placeholder strings before importing:

| Placeholder | Replace with |
|---|---|
| `https://YOUR_APP_DOMAIN` | Your deployed app URL, e.g. `https://hogs.vercel.app` |
| `YOUR_MARK_PAID_SECRET` | The value of `MARK_PAID_SECRET` from your `.env.local` |
| `YOUR_EMAIL@example.com` | The email address to receive success/failure alerts (appears twice) |

---

## How it works end-to-end

```
User buys tickets on site
        ↓
Order created in Supabase (status = "pending")
        ↓
User taps "Pay with Venmo" button → pays @Sir-Pork-A-Lot
        ↓
Venmo sends email → "You received $25.00 from John Doe"
        ↓
Power Automate picks it up (checks every 2 min)
        ↓
Parses name + amount from subject line
        ↓
POST /api/mark-paid  { name: "John Doe", amount: "25.00" }
        ↓
Supabase order updated → payment_status = "paid"
        ↓
You receive a confirmation email ✅
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| HTTP 401 from webhook | Wrong secret | Double-check `MARK_PAID_SECRET` in both `.env.local` and the flow |
| HTTP 404 from webhook | No matching pending order | Name in Venmo doesn't match name entered at checkout — update manually in Supabase |
| Flow never triggers | Wrong sender filter | Verify Venmo emails arrive from `venmo@venmo.com` in your inbox |
| Amount parse is wrong | Unexpected subject format | Test with a real Venmo email and adjust the `Extract_Amount` expression |

---

## One-time backfill from exported emails

If the Outlook trigger was down and you need to process missed messages, do not rely on
the trigger to replay old emails. Instead:

1. Export the missed Outlook messages as `.eml` files into a local folder.
2. Run:

        ```bash
        python dashboard/venmo_email_backfill.py --input path/to/exported-emails --output venmo_backfill.csv
        ```

3. Review rows where `ParseStatus = needs_review`.
4. Import the CSV into SharePoint or use it as the source for a one-time Power Automate backfill flow.

The CSV includes the same core fields used by the Venmo SharePoint flow:

- `Title`
- `Person`
- `NumberofChances`
- `PaymentReferenceID`
- `TotalPaid`
- `SubmissionDate`
- `EmailAddress`
- `RaffleName`
