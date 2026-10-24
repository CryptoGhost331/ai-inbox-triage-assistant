# Make.com scenario: AI Inbox Triage (drafts only)

## Import

1. In Make, open **Scenarios → Create a new scenario**.
2. Click the **⋯** menu at the bottom → **Import Blueprint** → choose
   `ai_inbox_triage_blueprint.json`.
3. Pick your connections on the three modules that need one:
   - **Gmail: Watch emails**, **Gmail: Get an email**, **Gmail: Create a draft**: your Google account
   - **Claude: Create a prompt**: your Anthropic API key
4. In the Claude module, check the **Model** dropdown and paste your own
   tone guide in place of the sample one in the prompt.
5. Click **Run once** with a test email in a copy or test mailbox first.
6. Turn on scheduling (e.g. every 15 minutes) when you're happy with the drafts.

## Flow

| # | Module | Notes |
|---|---|---|
| 1 | Gmail: Watch emails | Gmail search `in:inbox -category:promotions -category:social -category:updates -from:noreply -from:no-reply`, up to 10 per run |
| 2 | Gmail: Get an email | Full content: sender, subject, plain-text body, thread |
| 3 | Claude: Create a prompt | Style guide + first 2,000 characters of the body. Returns JSON |
| 6 | Break (error handler on 3) | 3 retries, 15 minutes apart, then stored as an incomplete execution |
| 4 | JSON: Parse JSON | Turns Claude's reply into `label`, `reason`, `summary`, `needs_reply`, `draft` |
| 5 | Gmail: Create a draft | Only when `needs_reply` is true. Saved in the same thread. **Never sent.** |

## Safeguards

- No send module anywhere in the scenario.
- **Data is confidential** is turned on, so email contents aren't kept in Make's execution logs.
- **Allow storing incomplete executions** is on, so a failed email is kept for replay instead of lost.
- Turn on Make's email notifications for errors (Profile → Notifications) for alerts.

## Optional add-ons

- Apply a Gmail label per category (`AI/urgent`, `AI/follow-up`, ...) with
  **Gmail: Update email labels** after step 4.
- Log every email to a Google Sheet with **Google Sheets: Add a row**.
- Send a daily digest of `urgent` items to Slack or email.

The blueprint passes Make's schema validation. Field mappings follow the
Gmail v4 and Anthropic Claude app modules; after import, open each module once
to confirm the mappings resolved with your connections.
