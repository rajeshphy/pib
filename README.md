# PIB

PIB is a tiny daily digest generator for the PIB regional news page:

<https://www.pib.gov.in/indexd.aspx?reg=48&lang=1>

It fetches the listing, asks Gemini for no more than five significant English points, and writes a Jekyll Markdown post under `docs/_posts/`.

## Local Run

Create `.env` locally:

```bash
GEMINI_API_KEY=your_key_here
# Optional override. The default is gemini-3.1-flash-lite.
GEMINI_MODEL=gemini-3.1-flash-lite
```

Then run:

```bash
./run.sh generate
```

Preview with Jekyll when installed:

```bash
./run.sh serve
```

Run without Gemini:

```bash
./run.sh no-ai
```

## GitHub Deployment

1. Push this `PIB` folder to a GitHub repository.
2. In the repository, open `Settings -> Secrets and variables -> Actions`.
3. Add a repository secret named `GEMINI_API_KEY`.
4. Open `Settings -> Pages`.
5. Set `Source` to `GitHub Actions`.
6. The workflow in `.github/workflows/daily.yml` runs every day and deploys the `docs` site.

The key should never be committed. If a real key was pasted into chat or logs, rotate it in Google AI Studio before relying on it.

## Quota

The project keeps its own small quota file in `data/quota.json`:

- minimum 12 seconds between Gemini calls, matching 5 requests per minute
- maximum 20 Gemini calls per UTC day

The normal daily run uses one Gemini request.
