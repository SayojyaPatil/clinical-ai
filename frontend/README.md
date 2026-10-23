# Clinical AI Frontend

A light, teal-accented React/TypeScript workspace connected to the existing FastAPI endpoints. Includes signup/login, text analysis, image upload, account-scoped history, and structured results.

## Run locally

From the repository root, start FastAPI in one terminal:

```bash
python -m uvicorn app.main:app --reload
```

In another terminal:

```bash
cd frontend
npm install
npm run dev
```

Open http://127.0.0.1:5173. Vite proxies requests from `/api/*` to `http://127.0.0.1:8000/*`, so no backend CORS changes are needed for local development.

The frontend stores JWTs in sessionStorage, checks expiry before restoration, and verifies restored sessions with GET /notes. Do not use identifiable patient data. OpenAI calls from Analyze incur API charges. For deployment, configure restricted access, secrets, secure token/session storage, rate limiting, persistence, and review safeguards.

Optional: `VITE_API_BASE_URL` can specify a different API prefix or URL. Do not store secrets in Vite environment variables.

## Document review (Stage 2)

Open **View original document** from any Analysis History row. The responsive,
read-only screen shows the original text/image next to the immutable AI output,
plus the recorded review status. Legacy image uploads explicitly show unavailable
originals; legacy extraction strings are displayed unchanged.

Source metadata comes from `GET /notes/{id}/source`; protected image bytes come
from `GET /notes/{id}/source/content` using the existing bearer token. Preview
object URLs are revoked when leaving, retrying, or switching documents. Image
controls support zoom and show filename, MIME type, byte size, checksum and native
dimensions. Stage 2 adds no editing, approval, or export controls.

Run the frontend tests with `node --test tests/*.test.cjs` and build with
`npm run build`. Tests use synthetic data and stubbed network responses; live
browser layout and assistive-technology checks are separate.
