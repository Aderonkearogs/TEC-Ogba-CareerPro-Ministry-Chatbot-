# CareerPro Ministry Chatbot — Render-ready (knowledge-base Q&A + separate job search)

## What this version does
- The main **Ask CareerPro** chat answers from the supplied `TEC OGBA CAREERPRO MINISTRY.docx`, extracted into `knowledge_base.txt`.
- Ministry Q&A does **not** call ChatGPT or web search. If no relevant knowledge-base section is found, it says the ministry should confirm.
- **Find a Job** is separate and opens a ChatGPT search prompt for current web results. The user should verify each vacancy on the employer's official careers page.
- Includes activity, business support, Enterprise Fund, mentorship, prayer/testimony form, and WhatsApp community sections.
- Includes `/health` for Render health checks.

## Deploy on Render
1. Upload/extract the contents of this ZIP into the root of your GitHub repository. Do not upload only the ZIP itself.
2. Ensure `app.py`, `knowledge_base.txt`, `requirements.txt`, `render.yaml`, and the `web` folder are visible at repository root.
3. In Render, create a new Blueprint from the GitHub repository, or set the web service:
   - Build command: `pip install -r requirements.txt`
   - Start command: `uvicorn app:app --host 0.0.0.0 --port $PORT`
4. Deploy, then test `/health` and the homepage.

## Important
- This job-search button opens ChatGPT in a new tab with a search prompt; it does not embed ChatGPT in the website or provide a private API integration. Visitors may need to sign in to ChatGPT.
- No OpenAI API key is required for knowledge-base Q&A.
- The knowledge-base retrieval is lightweight keyword-based retrieval over the supplied document, not a generative AI model. It returns matching excerpts to avoid inventing ministry facts.
- The 2027 dates and funding details are reproduced from the uploaded ministry document and should be updated by ministry administrators if plans change.
- Do not add secrets to GitHub. WhatsApp integration is not enabled in this version.
