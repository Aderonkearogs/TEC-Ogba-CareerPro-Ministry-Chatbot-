# Publish CareerPro Chatbot (Render + GitHub)

I cannot create the public URL without access to your hosting account, but this project now includes `render.yaml` to configure a Render web service.

1. Sign in to GitHub and create a **private or public** repository named `tec-ogba-careerpro-chatbot`.
2. Upload all project files from this folder to the repository root. Include `render.yaml`. Do not upload `.env` or any secret keys.
3. Sign in to Render at https://render.com/ and select **New → Blueprint** (or connect the repository as a Web Service).
4. Choose the GitHub repository and deploy. Render reads `render.yaml` and configures the start command and `/health` check.
5. After deployment, copy the actual `https://...onrender.com` URL shown in the Render dashboard. Open the root page and `/health` to test it.
6. Share that actual URL. Do not use an example URL as if it were live.

Important: this is a starter deployment. The live job search function is still a stub and will not return live vacancies until an authorised job source/API is connected. Obtain ministry approval before presenting it as an official church service. Do not add API keys to the repository; use Render's Environment settings.
