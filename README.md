# Customer Engagement Chatbot

A minimal chatbot with:

- a static HTML/CSS/JavaScript frontend deployed to GitHub Pages;
- a Python REST API deployed as a Vercel Function; and
- Anthropic's Messages API, called only from the backend.

The Anthropic API key is never sent to the browser or committed to Git.

## Repository layout

```text
frontend/                 GitHub Pages application
backend/api/index.py      Vercel Python Function
backend/requirements.txt  Python production dependency
.github/workflows/        CI and GitHub Pages deployment
```

## 1. Deploy the backend to Vercel

1. In Vercel, select **Add New > Project**.
2. Import this GitHub repository.
3. Set **Root Directory** to `backend`.
4. In **Settings > Environment Variables**, add:

   | Variable | Value |
   | --- | --- |
   | `ANTHROPIC_API_KEY` | Your secret Anthropic API key |
   | `ANTHROPIC_MODEL` | A current model ID available to your Anthropic account |
   | `ALLOWED_ORIGINS` | `https://YOUR_GITHUB_USERNAME.github.io` |
   | `MAX_OUTPUT_TOKENS` | `600` |
   | `MAX_INPUT_CHARACTERS` | `12000` |

5. Apply the variables to Production, Preview, and Development as appropriate.
6. Deploy the project.
7. Verify `https://YOUR_VERCEL_PROJECT.vercel.app/api`.

Environment variable changes apply only to new deployments. Redeploy after
changing one. Never put `ANTHROPIC_API_KEY` in the frontend or a GitHub Pages
variable.

## 2. Connect the frontend

Edit `frontend/config.js`:

```js
window.APP_CONFIG = {
  apiBaseUrl: "https://YOUR_VERCEL_PROJECT.vercel.app",
};
```

The Vercel URL is public and safe to commit. Commit and push the change.

## 3. Enable GitHub Pages

1. Open the GitHub repository.
2. Select **Settings > Pages**.
3. Under **Build and deployment**, set **Source** to **GitHub Actions**.
4. Open **Actions** and verify the `Deploy frontend to GitHub Pages` workflow.

The workflow publishes only the `frontend` directory on pushes to `main`.

## Local development

Copy the example environment file and insert your own values:

```bash
cp backend/.env.example backend/.env.local
```

Do not commit `.env.local`. To run the static frontend:

```bash
python3 -m http.server 8000 --directory frontend
```

For local API work, install `backend/requirements.txt` into a virtual
environment and use Vercel CLI (`vercel dev`) from `backend`.

Set the local allowed origin to:

```text
http://localhost:8000
```

To allow both local development and GitHub Pages, use a comma-separated value:

```text
http://localhost:8000,https://YOUR_GITHUB_USERNAME.github.io
```

## API

### `GET /api`

Returns:

```json
{"status":"ok"}
```

### `POST /api`

Request:

```json
{
  "messages": [
    {"role": "user", "content": "Hello"}
  ]
}
```

Response:

```json
{"reply":"Hello! How can I help?"}
```

The API validates message roles, message size, total input size, content type,
and request origin. CORS limits browser access but is not authentication.
Before sharing the chatbot widely, add durable rate limiting or authentication
and configure an Anthropic spending limit.

## Tests

Run:

```bash
python3 -m unittest discover -s tests -v
```
