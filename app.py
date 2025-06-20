import os
import re
import logging
import requests
from flask import Flask, request, jsonify
from urllib.parse import urlparse, parse_qs
from dotenv import load_dotenv
from youtube_transcript_api import (
    YouTubeTranscriptApi,
    TranscriptsDisabled,
    NoTranscriptFound
)
from youtube_transcript_api.proxies import WebshareProxyConfig

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)

# Load proxy credentials
PROXY_USER = os.getenv("PROXY_USERNAME")
PROXY_PASS = os.getenv("PROXY_PASSWORD")
PROXY_HOST = os.getenv("PROXY_HOST", "p.webshare.io:80")

if not PROXY_USER or not PROXY_PASS:
    logger.warning("Proxy credentials missing. This will break transcript requests!")

# Initialize proxy-enabled YouTubeTranscriptApi client
ytt_api = YouTubeTranscriptApi(
    proxy_config=WebshareProxyConfig(
        proxy_username=PROXY_USER,
        proxy_password=PROXY_PASS
    )
)

# Extract YouTube video ID from URL
def extract_video_id_from_url(url):
    try:
        parsed = urlparse(url)
        if parsed.hostname in ["www.youtube.com", "youtube.com"]:
            return parse_qs(parsed.query).get("v", [None])[0]
        elif parsed.hostname == "youtu.be":
            return parsed.path.lstrip("/")
        return None
    except Exception as e:
        logger.exception("Failed to extract video ID")
        return None

# Clean up text for flat or structured transcript
def clean_text(text):
    text = text.replace("\n", " ").replace("\\", "")
    return re.sub(r"[^\x00-\x7F]+", "", text)

@app.route("/api/transcript", methods=["GET"])
def get_transcript():
    # Parse params safely from raw query
    video_id = request.args.get("videoId")
    full_query = request.query_string.decode()
    params = parse_qs(full_query)
    url = params.get("url", [None])[0]
    lang = request.args.get("lang", "en")
    flat_text = params.get("flat_text", ["false"])[0].lower() == "true"

    logger.info("Request: videoId=%s, url=%s, lang=%s, flat_text=%s", video_id, url, lang, flat_text)

    if not video_id and not url:
        return jsonify({"success": False, "error": "YouTube video ID or URL is required"}), 200

    if not video_id:
        video_id = extract_video_id_from_url(url)
        if not video_id:
            return jsonify({"success": False, "error": "Invalid YouTube video URL"}), 200

    if lang not in ["en", "cn", "ok"]:
        lang = "en"

    # Optional connectivity test (enable with DEBUG_CONNECTIVITY=true)
    if os.getenv("DEBUG_CONNECTIVITY", "false").lower() == "true":
        try:
            response = requests.get("https://www.youtube.com", timeout=5, proxies={
                "http": f"http://{PROXY_USER}:{PROXY_PASS}@{PROXY_HOST}",
                "https": f"http://{PROXY_USER}:{PROXY_PASS}@{PROXY_HOST}"
            })
            logger.info("Connectivity test to YouTube: %s", response.status_code)
        except Exception as e:
            logger.warning("Connectivity test failed: %s", str(e))

    try:
        transcript = ytt_api.get_transcript(video_id, languages=[lang])
        logger.info("Fetched transcript with %d segments", len(transcript))

        if flat_text:
            text_output = " ".join(clean_text(item["text"]) for item in transcript)
            return jsonify({"success": True, "transcript": text_output})

        structured_output = [
            {
                "text": clean_text(item["text"]),
                "duration": round(item["duration"], 2),
                "offset": round(item["start"], 2),
                "lang": lang
            }
            for item in transcript
        ]
        return jsonify({"success": True, "transcript": structured_output})

    except (TranscriptsDisabled, NoTranscriptFound):
        return jsonify({"success": False, "error": "Failed to fetch transcript"}), 200
    except Exception as e:
        logger.exception("Unexpected error during transcript fetch")
        return jsonify({"success": False, "error": str(e)}), 200

# Note: No debug=True here. Vercel/Gunicorn should launch the app.

if __name__ == "__main__":
    logger.info("Starting Flask development server on http://0.0.0.0:5000")
    app.run(host="0.0.0.0", port=5000)
