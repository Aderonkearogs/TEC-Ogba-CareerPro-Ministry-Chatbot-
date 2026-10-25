# The Elevation Church Ogba CareerPro Ministry Chatbot

This is a deployable starter project for a public website plus WhatsApp Business Platform webhook.

## Important current limitation

The web interface and API are scaffolded, but `job_sources.search_jobs()` intentionally returns no vacancies. It must be connected to an authorised API/feed or permitted employer career-site integration before it can show live jobs. Do not claim a listing is verified unless the source confirms the employer and the specific vacancy.

Obtain church/ministry approval before presenting the site as an official service.

## 1. Run locally

Requirements: Python 3.11+.

```bash
python -m venv .venv
# macOS/Linux:
source .venv/bin/activate
# Windows PowerShell:
# .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env
uvicorn app:app --reload --port 8000
```

Open http://127.0.0.1:8000. `/health` should return a JSON status.

## 2. Publish on Render

1. Create a GitHub repository and upload these files. Do not upload `.env`.
2. Sign in to Render and choose **New > Web Service**.
3. Connect the repository.
4. Set **Build Command** to `pip install -r requirements.txt`.
5. Set **Start Command** to `uvicorn app:app --host 0.0.0.0 --port $PORT`.
6. Add environment variables from `.env.example` in Render's Environment settings. Leave WhatsApp fields blank until Meta setup is complete.
7. Deploy. Render will assign a real `https://...onrender.com` URL. Open it and `/health` to verify.
8. Use the actual deployed URL in Meta's webhook configuration; do not guess the URL.

## 3. Set up WhatsApp Cloud API

1. Visit https://developers.facebook.com/ and create/sign in to a Meta developer account.
2. Create an app and add the WhatsApp product; use the test number first.
3. Follow the current Meta setup guide to obtain a temporary test access token, phone-number ID, and WhatsApp Business Account details.
4. Set `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_VERIFY_TOKEN`, `WHATSAPP_APP_SECRET`, and `GRAPH_API_VERSION` in Render's secret environment variables.
5. Configure the callback URL as `https://YOUR-DEPLOYED-DOMAIN/webhook`, and enter the exact `WHATSAPP_VERIFY_TOKEN` value. Subscribe to the `messages` webhook field.
6. Ensure Meta app webhook signature verification succeeds. This code requires `WHATSAPP_APP_SECRET`; test with Meta's real signed webhook.
7. Send a test message from an allowed tester. Confirm a reply arrives. Use a production token and registered business number only after the test flow is working and the required Meta business/account steps are complete.
8. Review current WhatsApp opt-in, user-initiated service-window, template, pricing, and business policies before launching.

Official starting point: https://whatsappbusiness.com/developers/developer-hub/

## 4. Connect live job sources

Implement `search_jobs(query)` in `job_sources.py` using an authorised partner API/feed or permitted employer career-site integration. For every job, populate:
- employer name and official source URL
- direct application URL
- posting and closing dates when available
- work arrangement and location
- `employer_verified=True` only with evidence of employer identity
- `vacancy_confirmed=True` only when the specific role is confirmed on an authorised source

Use HTTPS and verify redirects/domains. HTTPS alone is not evidence of a real vacancy. Do not scrape job boards without permission. Add persistence, deduplication, source evidence, expiry checks, retries/queueing, and monitoring before production.

## 5. Create a share link and QR code only after deployment

Use the exact Render URL shown on the service dashboard after deployment and testing. Once the public destination is confirmed, create a QR code from that exact URL. For WhatsApp, a `wa.me` link requires the actual registered business phone number in international digits; do not invent a number. A QR code can point to the website, or directly to WhatsApp once the real number is available.
