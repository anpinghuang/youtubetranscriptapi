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

app = Flask(__name__)

# Proxy setup
PROXY_USER = os.getenv("PROXY_USERNAME")
PROXY_PASS = os.getenv("PROXY_PASSWORD")
PROXY_HOST = os.getenv("PROXY_HOST", "p.webshare.io:80")
proxy_url = f"http://{PROXY_USER}:{PROXY_PASS}@{PROXY_HOST}"
proxies = {"http": proxy_url, "https": proxy_url}

# Check proxy
if not PROXY_USER or not PROXY_PASS:
    logger.warning("Proxy credentials missing. This will break transcript requests!")

# Create proxied API
ytt_api = YouTubeTranscriptApi(
    proxy_config=WebshareProxyConfig(
        proxy_username=PROXY_USER,
        proxy_password=PROXY_PASS
    )
)

def get_proxy_ip():
    try:
        resp = requests.get("https://api.ipify.org?format=json", proxies=proxies, timeout=5)
        return resp.json().get("ip", "Unavailable")
    except Exception as e:
        logger.warning("Failed to fetch proxy IP: %s", str(e))
        return "Unavailable"

def get_direct_ip():
    try:
        resp = requests.get("https://api.ipify.org?format=json", timeout=5)
        return resp.json().get("ip", "Unavailable")
    except Exception:
        return "Unavailable"

def extract_video_id_from_url(url):
    try:
        parsed = urlparse(url)
        if parsed.hostname in ["www.youtube.com", "youtube.com"]:
            return parse_qs(parsed.query).get("v", [None])[0]
        elif parsed.hostname == "youtu.be":
            return parsed.path.lstrip("/")
        return None
    except Exception:
        return None

def clean_text(text):
    text = text.replace("\n", " ").replace("\\", "")
    return re.sub(r"[^\x00-\x7F]+", "", text)

@app.route("/api/transcript", methods=["GET"])
def get_transcript():
    proxy_ip = get_proxy_ip()
    server_ip = get_direct_ip()
    logger.info(f"Proxy IP: {proxy_ip} | Server IP: {server_ip}")

    video_id = request.args.get("videoId")
    full_query = request.query_string.decode()
    params = parse_qs(full_query)
    url = params.get("url", [None])[0]
    lang = request.args.get("lang", "en")
    flat_text = params.get("flat_text", ["false"])[0].lower() == "true"

    if not video_id and url:
        video_id = extract_video_id_from_url(url)

    if not video_id:
        return jsonify({"success": False, "error": "YouTube video ID or URL is required"}), 200

    try:
        transcript = ytt_api.get_transcript(video_id, languages=[lang])
        logger.info("Transcript found with %d segments", len(transcript))

        if flat_text:
            text_output = " ".join(clean_text(item["text"]) for item in transcript)
            return jsonify({
                "success": True,
                "proxy_ip": proxy_ip,
                "server_ip": server_ip,
                "transcript": text_output
            })

        structured_output = [
            {
                "text": clean_text(item["text"]),
                "duration": round(item["duration"], 2),
                "offset": round(item["start"], 2),
                "lang": lang
            }
            for item in transcript
        ]
        return jsonify({
            "success": True,
            "proxy_ip": proxy_ip,
            "server_ip": server_ip,
            "transcript": structured_output
        })

    except (TranscriptsDisabled, NoTranscriptFound):
        return jsonify({"success": False, "error": "No transcript available"}), 200
    except Exception as e:
        logger.exception("Error fetching transcript")
        return jsonify({"success": False, "error": str(e)}), 200

if __name__ == "__main__":
    logger.info("Starting Flask server on http://0.0.0.0:5000")
    app.run(host="0.0.0.0", port=5000)
