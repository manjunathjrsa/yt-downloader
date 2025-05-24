import os
import re
import uuid
import tempfile
from flask import Flask, request, jsonify, send_from_directory, Response
import yt_dlp
from flask_cors import CORS
from threading import Lock

app = Flask(__name__, static_folder='static')
CORS(app, resources={r"/*": {"origins": "*"}})

# Thread-safe progress tracking
progress_data = {}
progress_lock = Lock()

def progress_hook(d):
    if d['status'] == 'downloading':
        video_id = d['info_dict']['id']
        with progress_lock:
            progress_data[video_id] = {
                'percent': d.get('_percent_str', '0%'),
                'speed': d.get('_speed_str', 'N/A'),
                'eta': d.get('_eta_str', 'N/A')
            }

def validate_youtube_url(url):
    """Validate YouTube URL with comprehensive patterns"""
    patterns = [
        r'(https?://)?(www\.)?(youtube\.com|youtu\.be)/watch\?v=[\w-]+',
        r'(https?://)?(www\.)?youtu\.be/[\w-]+',
        r'(https?://)?(www\.)?youtube\.com/embed/[\w-]+',
        r'(https?://)?(www\.)?youtube\.com/v/[\w-]+',
        r'(https?://)?(www\.)?youtube\.com/playlist\?list=[\w-]+',
        r'(https?://)?(www\.)?youtube\.com/shorts/[\w-]+'
    ]
    return any(re.match(pattern, url) for pattern in patterns)

@app.route('/')
def serve_frontend():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/download', methods=['POST'])
def download_video():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Invalid request data'}), 400

        url = data.get('url', '').strip()
        quality = data.get('quality', '720')
        video_id = data.get('video_id', str(uuid.uuid4()))

        # Enhanced URL validation
        if not url:
            return jsonify({'error': 'URL is required'}), 400

        if not validate_youtube_url(url):
            return jsonify({'error': 'Invalid YouTube URL format. Supported formats:\n'
                              '- https://www.youtube.com/watch?v=VIDEO_ID\n'
                              '- https://youtu.be/VIDEO_ID\n'
                              '- https://www.youtube.com/embed/VIDEO_ID\n'
                              '- https://www.youtube.com/playlist?list=PLAYLIST_ID'}), 400

        ydl_opts = {
            'format': get_format(quality),
            'progress_hooks': [progress_hook],
            'quiet': True,
            'noplaylist': True,
            'outtmpl': os.path.join(tempfile.gettempdir(), f'{video_id}.%(ext)s'),
            'http_chunk_size': 1048576  # 1MB chunks for streaming
        }

        def generate():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                try:
                    info = ydl.extract_info(url, download=True)
                    filename = ydl.prepare_filename(info)
                    
                    with open(filename, 'rb') as f:
                        while chunk := f.read(1024 * 1024):  # 1MB chunks
                            yield chunk
                finally:
                    # Cleanup
                    try:
                        os.remove(filename)
                    except:
                        pass

        return Response(generate(), mimetype='video/mp4')

    except yt_dlp.utils.DownloadError as e:
        return jsonify({'error': f'YouTube download error: {str(e)}'}), 400
    except Exception as e:
        return jsonify({'error': f'Server error: {str(e)}'}), 500

def get_format(quality):
    return {
        '480': 'bestvideo[height<=480]+bestaudio/best[height<=480]',
        '720': 'bestvideo[height<=720]+bestaudio/best[height<=720]',
        '1080': 'bestvideo[height<=1080]+bestaudio/best[height<=1080]',
    }.get(quality, 'best')

@app.route('/progress/<video_id>')
def get_progress(video_id):
    with progress_lock:
        return jsonify(progress_data.get(video_id, {}))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
