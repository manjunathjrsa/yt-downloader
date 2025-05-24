import os
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

@app.route('/')
def serve_frontend():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/download', methods=['POST'])
def download_video():
    try:
        data = request.json
        url = data['url']
        quality = data['quality']
        video_id = data['video_id']

        if not url or not all(x in url for x in ('youtube.com', 'youtu.be')):
            return jsonify({'error': 'Invalid YouTube URL'}), 400

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
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)
                
                # Stream the file in chunks
                with open(filename, 'rb') as f:
                    while chunk := f.read(1024 * 1024):  # 1MB chunks
                        yield chunk
                
                # Cleanup
                try:
                    os.remove(filename)
                except:
                    pass

        return Response(generate(), mimetype='video/mp4')

    except Exception as e:
        return jsonify({'error': str(e)}), 500

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