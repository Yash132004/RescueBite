# Run the RescueBite help chatbot with Gemini

This guide applies to the Django project in this folder (the directory containing `manage.py`). The chatbot uses the existing OpenAI Python SDK with Google's OpenAI-compatible Gemini endpoint. The API key stays in the server process environment; never paste it into Django settings, source files, templates, or chat messages.

## 1. Create a Gemini API key

Create or copy a Gemini API key in [Google AI Studio](https://aistudio.google.com/app/apikey). Keep it private. Gemini API access, model availability, and quotas are controlled by your Google account/project.

## 2. Open PowerShell in the Django project directory

Change to the folder that contains `manage.py`, for example:

```powershell
Set-Location 'C:\Users\rk care\OneDrive\Desktop\RescueBiteProject\RescueBite\myproject'
```

The configured Python environment must have the packages from `requirements.txt` installed. The repository already includes the OpenAI SDK, numpy, and rank_bm25; no additional provider package is needed.

## 3. Add the key and generation model to `.env`

Open the `.env` file beside `manage.py`. The project now loads this file when Django starts. Set the key and model there:

```powershell
GEMINI_API_KEY=put-your-key-here
GEMINI_MODEL=gemini-3.8-flash
```

Replace `put-your-key-here` with your Google AI Studio key. `.env` is git-ignored. Do not commit it or share its contents. A `GEMINI_API_KEY` or `GEMINI_MODEL` already set in the process environment takes precedence over the file.

`GEMINI_EMBEDDING_MODEL` defaults to `gemini-embedding-001`, and `GEMINI_BASE_URL` defaults to `https://generativelanguage.googleapis.com/v1beta/openai/`; you normally do not need to add either setting to `.env`.

## 4. Build the local knowledge index

Run this after setting the key, from the project directory:

```powershell
python manage.py build_help_index
python manage.py build_help_index --check
```

The first command reads `RESCUEBITE_PRODUCT_CONTEXT.md`, embeds its indexable sections, and saves the index under `.help_index`. It sends the context text to Gemini for embeddings. It does not send user, account, or donation records. Batches are deliberately small, with limited retry on rate limits. The check command verifies both the source document and configured embedding model match the saved index.

If you change `GEMINI_EMBEDDING_MODEL`, rebuild the index before using the chatbot. Embeddings from different models cannot be mixed.

## 5. Start the application and try the chat

```powershell
python manage.py runserver
```

Open the local home page and use the **May I Help You?** chat. Ask a question answered by the product context, such as “How does an NGO claim a donation?” The endpoint remains `/help/chat/`; the key is only used server-side.

## 6. Run the live evaluation (optional)

```powershell
python manage.py eval_help_bot
```

This sends the evaluation questions to Gemini and uses API quota. It prints each best cosine score, the minimum score for answerable questions, the maximum for out-of-scope questions, and a suggested midpoint threshold. The checked-in threshold remains provisional until you inspect these live results; do not change it blindly. If the ranges overlap, retrieval alone does not cleanly separate those categories.

## Troubleshooting

- **Chat shows its connection fallback:** confirm `GEMINI_API_KEY` is set in the same PowerShell window that runs Django. Check server logs for a short error category.
- **Index missing or stale:** run `python manage.py build_help_index`, then `python manage.py build_help_index --check`.
- **Embedding-model mismatch:** ensure the model environment setting is consistent between index creation and server startup; rebuild the index.
- **Rate limit or quota:** wait for the quota window or check Google AI Studio project limits, then retry index creation.
- **Authentication failure:** create/replace the key in Google AI Studio and set it again in the current PowerShell session. Do not send the key to anyone.

## Verified defaults

Google's official documentation lists `gemini-3.8-flash` and `gemini-embedding-001` as model IDs and documents chat completions and embeddings through the OpenAI-compatible base URL. Gemini 3.8 supports low, medium, and high thinking levels; the chatbot requests low to reduce response latency. Availability and quota still depend on the key's project.

If the chat times out, restart Django after changing `.env`; the chatbot allows 45 seconds for Gemini responses. A 503 indicates temporary provider unavailability, so retry later. The embedding model default is listed as stable.

