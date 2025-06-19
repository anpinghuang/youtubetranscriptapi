from flask import Flask, request, jsonify
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
from youtube_transcript_api.proxies import WebshareProxyConfig
from urllib.parse import urlparse, parse_qs
import os, re

app = Flask(__name__)

# Extract video ID
def extract_video_id_from_url(url):
    try:
        parsed = urlparse(url)
        if parsed.hostname in ["www.youtube.com", "youtube.com"]:
            return parse_qs(parsed.query).get("v", [None])[0]
        elif parsed.hostname == "youtu.be":
            return parsed.path.lstrip("/")
    except:
        return None

# Text cleanup
def clean_text(text):
    text = text.replace("\n", " ").replace("\\", "")
    return re.sub(r"[^\x00-\x7F]+", "", text)

# Proxy credentials (use env vars in production!)
PROXY_USER = os.getenv("PROXY_USERNAME", "sbotnpxp-1")
PROXY_PASS = os.getenv("PROXY_PASSWORD", "k4curnl28y8z")

# Initialize proxy-enabled API client
ytt_api = YouTubeTranscriptApi(
    proxy_config=WebshareProxyConfig(
        proxy_username=PROXY_USER,
        proxy_password=PROXY_PASS
    )
)

@app.route("/api/transcript", methods=["GET"])
def get_transcript():
    video_id = request.args.get("videoId")
    url = request.args.get("url")
    lang = request.args.get("lang", "en")
    flat_text = request.args.get("flat_text", "").lower() == "true"

    if not video_id and not url:
        return jsonify({"success": False, "error": "YouTube video ID or URL is required"}), 200

    if not video_id:
        video_id = extract_video_id_from_url(url)
        if not video_id:
            return jsonify({"success": False, "error": "Invalid YouTube video URL"}), 200

    if lang not in ["en", "cn", "ok"]:
        lang = "en"

    try:
        transcript = ytt_api.get_transcript(video_id, languages=[lang])

        if flat_text:
            raw = " ".join(clean_text(item["text"]) for item in transcript)
            return jsonify({"success": True, "transcript": raw})

        formatted = [
            {
                "text": clean_text(item["text"]),
                "duration": round(item["duration"], 2),
                "offset": round(item["start"], 2),
                "lang": lang
            }
            for item in transcript
        ]
        return jsonify({"success": True, "transcript": formatted})

    except (TranscriptsDisabled, NoTranscriptFound):
        return jsonify({"success": False, "error": "Failed to fetch transcript"}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 200

if __name__ == "__main__":
    app.run(debug=True)
