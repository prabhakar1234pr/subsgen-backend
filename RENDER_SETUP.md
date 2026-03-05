# SubsGen on Render

## You do NOT need a Render API key for deployment

Render deploys by connecting your GitHub repo. No API key required.

## Setup Steps

### 1. Deploy the backend

1. Go to [dashboard.render.com](https://dashboard.render.com/)
2. Sign up or log in (use GitHub)
3. Click **New** → **Blueprint**
4. Connect your GitHub account if needed
5. Select repo: **prabhakar1234pr/subsgen-backend**
6. Render will detect `render.yaml` at the root
7. Click **Deploy Blueprint**
8. When prompted for env vars, add your Groq keys:
   - `GROQ_API_KEY_1`, `GROQ_API_KEY_2`, `GROQ_API_KEY_3` (recommended)
   - OR `GROQ_API_KEY` (single key)
9. Wait for the first deploy (~5–10 min)

### 2. Get your backend URL

After deploy, your API will be at:
```
https://subsgen-api-XXXX.onrender.com
```
(Find it in the Render Dashboard → your service → URL)

### 3. Update frontend

In **Vercel** (or wherever the frontend is deployed):
- Add env var: `BACKEND_URL` = `https://subsgen-api-XXXX.onrender.com`
- Redeploy the frontend

### 4. (Optional) Render API key

Only needed if you want to trigger deploys or manage services via the API:

1. [dashboard.render.com](https://dashboard.render.com/) → **Account Settings** (top right)
2. **API Keys** → **Create API Key**
3. Copy and store it securely

For normal use (GitHub → auto-deploy on push), you don’t need this.
