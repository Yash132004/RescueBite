import json

from django.http import JsonResponse
from django.views.decorators.http import require_POST

from .services.chatbot import FALLBACK_MESSAGE, MAX_MESSAGE_LENGTH, ask_help


@require_POST
def chatbot_message(request):
    """Handle one anonymous, non-persistent help question."""
    if request.content_type != "application/json":
        return JsonResponse({"error": "Send a JSON message."}, status=400)
    try:
        payload = json.loads(request.body or b"{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "That message could not be read."}, status=400)
    if not isinstance(payload, dict):
        return JsonResponse({"error": "Send a JSON message."}, status=400)

    message = payload.get("message")
    if not isinstance(message, str) or not message.strip():
        return JsonResponse({"error": "Enter a question to continue."}, status=400)
    message = message.strip()
    if len(message) > MAX_MESSAGE_LENGTH:
        return JsonResponse({
            "error": f"Please keep your question under {MAX_MESSAGE_LENGTH} characters."
        }, status=400)

    return JsonResponse({"reply": ask_help(message) or FALLBACK_MESSAGE})
