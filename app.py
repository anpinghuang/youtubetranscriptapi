from flask import Flask, request, jsonify
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
from urllib.parse import urlparse, parse_qs
import re


app = Flask(__name__)

def extract_video_id_from_url(url):
    """Extract YouTube video ID from a given URL."""
    try:
        parsed_url = urlparse(url)
        if parsed_url.hostname in ["www.youtube.com", "youtube.com"]:
            return parse_qs(parsed_url.query).get("v", [None])[0]
        elif parsed_url.hostname == "youtu.be":
            return parsed_url.path.lstrip("/")
    except:
        return None

@app.route("/api/transcript", methods=["GET"])
def get_transcript():
    video_id = request.args.get("videoId")
    url = request.args.get("url")
    lang = request.args.get("lang", "en")
    flat_text = request.args.get("flat_text", "false").lower() == "true"

    if not video_id and not url:
        return jsonify({"success": False, "error": "YouTube video ID or URL is required"}), 200

    if not video_id and url:
        video_id = extract_video_id_from_url(url)
        if not video_id:
            return jsonify({"success": False, "error": "Invalid YouTube video URL"}), 200

    supported_langs = ["en", "cn", "ok"]
    if lang not in supported_langs:
        lang = "en"

    try:
        transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=[lang])


        if flat_text:
            # Join text, remove newlines, strip non-ASCII characters
            raw_text = " ".join(item["text"].replace("\n", " ") for item in transcript)
            # Remove non-ASCII characters like \u2026, \u2014, etc.
            clean_text = re.sub(r"[^\x00-\x7F]+", "", raw_text)
            return jsonify({"success": True, "transcript": clean_text})


        def clean_text(text):
            text = text.replace("\n", " ")          # Remove newlines
            text = text.replace("\\", "")           # Remove backslashes
            text = re.sub(r"[^\x00-\x7F]+", "", text)  # Remove non-ASCII chars
            return text

        formatted_transcript = [
            {
                "text": clean_text(item["text"]),
                "duration": round(item["duration"], 2),
                "offset": round(item["start"], 2),
                "lang": lang
            }
            for item in transcript
        ]
        return jsonify({"success": True, "transcript": formatted_transcript})

    except (TranscriptsDisabled, NoTranscriptFound):
        return jsonify({"success": False, "error": "Failed to fetch transcript"}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 200

if __name__ == "__main__":
    app.run(debug=True)
