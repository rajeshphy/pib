# `src/` Code Structure

This folder contains the Python source code for the PIB digest generator.  The original project had most of the logic inside one large `main.py`; it has now been divided into smaller files so that each responsibility is easier to inspect, test, and edit.

The generated Jekyll posts are still written to the same original location:

```text
docs/_posts/
```

This is important because the GitHub Pages/Jekyll site expects posts in that directory.

---

## Folder layout

```text
src/
├── __init__.py
├── ai.py
├── common.py
├── directlink.py
├── fetch.py
├── filter.py
├── main.py
├── markdown.py
└── README.md
```

---

## Overall workflow

The workflow is:

```text
fetch.py
   ↓
directlink.py
   ↓
filter.py
   ↓
ai.py
   ↓
markdown.py
   ↓
docs/_posts/YYYY-MM-DD-pib-digest.md
```

`main.py` connects these steps.  It should remain small and should not again become the place where all logic is mixed together.

---

## `main.py`

`main.py` is the entry point.

Run from the repository root:

```bash
python src/main.py
```

Run without Gemini, useful for testing:

```bash
python src/main.py --no-ai
```

Run with fewer headlines:

```bash
python src/main.py --no-ai --limit 5
```

Main responsibilities:

1. Read command-line options.
2. Load `.env` if present.
3. Fetch PIB items through `fetch.py`.
4. Resolve source links unless `--no-resolve-links` is used.
5. Generate an AI summary through `ai.py`, or fallback headline bullets through `filter.py`.
6. Write the Jekyll post through `markdown.py`.

---

## `common.py`

`common.py` stores shared constants and small shared utilities.

Important values:

```python
PIB_URL = "https://www.pib.gov.in/indexd.aspx?reg=48&lang=1"
POSTS = DOCS / "_posts"
```

The `POSTS` constant preserves the original post output directory:

```text
docs/_posts/
```

It also defines the `NewsItem` dataclass:

```python
@dataclass(slots=True)
class NewsItem:
    title: str
    url: str
    date: str = ""
```

The rest of the project passes news entries using this structure.

---

## `fetch.py`

`fetch.py` downloads and parses the PIB regional listing page.

Responsibilities:

- Open the PIB regional listing page.
- Parse article links from the HTML.
- Keep only real PIB news links.
- Remove duplicate headlines.
- Optionally resolve each link through `directlink.py`.

The important function is:

```python
collect_items(limit: int, resolve_links: bool = True) -> list[NewsItem]
```

When `resolve_links=True`, each item’s URL is passed to:

```python
resolve_direct_url(item.url)
```

This ensures final posts contain direct article URLs, not broken or temporary redirect URLs.

---

## `directlink.py`

`directlink.py` is the most important file for source-link correctness.

Its purpose is:

```text
RSS/indirect/listing link → open/follow/inspect → direct article link
```

Public functions:

```python
resolve_direct_url(url: str) -> str
resolve_direct_link(url: str) -> str
resolve_direct_links_for_items(items)
choose_best_link(item)
```

### Corrected PIB behavior

The earlier version forced PIB links into this pattern:

```text
https://www.pib.gov.in/PressReleasePage.aspx?PRID=...
```

That caused this error in the browser:

```text
The specified URL cannot be found
```

The corrected version now preserves the safe PIB detail endpoint:

```text
https://www.pib.gov.in/PressReleaseDetail.aspx?PRID=...&lang=1&reg=48
```

Therefore, this file must **not** forcibly convert `PressReleaseDetail.aspx` into `PressReleasePage.aspx`.

### What it does for one link

For each input URL, `resolve_direct_url()` does this:

1. Cleans HTML-escaped URL separators such as `&amp;`.
2. Avoids the dangerous `&reg` to `®` corruption problem.
3. Extracts embedded target links from redirect parameters like `?url=...`, `?target=...`, or `?redirect=...`.
4. If the link is a PIB press release, returns a clean `PressReleaseDetail.aspx?PRID=...&lang=...&reg=...` URL.
5. If it is not already a direct PIB link, opens it and follows HTTP redirects.
6. Reads canonical or Open Graph URLs from the final HTML page where useful.
7. Falls back safely to the best normalized URL if network access fails.

### Manual test

```bash
python src/directlink.py "https://www.pib.gov.in/PressReleaseDetail.aspx?PRID=2275248&amp;lang=1&amp;reg=6"
```

Expected style of output:

```text
https://www.pib.gov.in/PressReleaseDetail.aspx?PRID=2275248&lang=1&reg=6
```

---

## `filter.py`

`filter.py` contains text and summary helpers.

Responsibilities:

- Clean text.
- Convert all-caps PIB titles into readable title case where needed.
- Extract source numbers like `[1]`, `[3]` from Gemini output.
- Infer source numbers when fallback text has no explicit source reference.
- Build fallback headline summaries when Gemini is not used or fails.
- Build a short post title and summary line.

The fallback mode is important because it allows:

```bash
python src/main.py --no-ai
```

This is useful for testing the generator without spending AI calls.

---

## `ai.py`

`ai.py` handles Gemini integration.

Responsibilities:

- Load `.env` values.
- Enforce the small local quota stored in `data/quota.json`.
- Build the Gemini prompt.
- Ask Gemini for a short English Markdown digest.
- Return the generated text to `main.py`.

The prompt asks Gemini to:

- Produce a one-line digest title.
- Write no more than five important points.
- Keep the summary factual.
- Avoid adding unsupported facts.
- End bullets with source numbers like `Sources: [1], [3]`.

The source-number rule is important because `markdown.py` converts those source numbers into source chips.

---

## `markdown.py`

`markdown.py` writes the final Jekyll post.

Responsibilities:

- Build YAML front matter.
- Preserve the original post layout and CSS classes.
- Convert Markdown bullets into HTML list items.
- Add source chips beside digest points.
- Add a final source list.
- Save the file under `docs/_posts/`.

The original visual structure is preserved using these classes:

```html
<p class="digest-meta">...</p>
<ul class="digest-points">...</ul>
<span class="source-chips">...</span>
<ul class="source-list">...</ul>
```

Source links are written with:

```html
<a href="..." target="_blank" rel="noopener noreferrer">Source</a>
```

So links open in a new tab and do not try to open inside an iframe.

---

## Testing checklist

### 1. Syntax check

```bash
python -m compileall src
```

### 2. Direct-link test

```bash
python src/directlink.py "https://www.pib.gov.in/PressReleaseDetail.aspx?PRID=2275248&amp;lang=1&amp;reg=6"
```

The output should remain a `PressReleaseDetail.aspx` link, not `PressReleasePage.aspx`.

### 3. Generate without AI

```bash
python src/main.py --no-ai --limit 5
```

Then check:

```text
docs/_posts/
```

### 4. Check post appearance

The generated post should still contain:

```html
# PIB Brief
<p class="digest-meta">...</p>
<ul class="digest-points">
<span class="source-chips">
## Source
<ul class="source-list">
```

These preserve the original post look.

---

## Most common source-link mistake

Do not change PIB links to this:

```text
PressReleasePage.aspx?PRID=...
```

Use this instead:

```text
PressReleaseDetail.aspx?PRID=...
```

That is the main correction made in this version.
