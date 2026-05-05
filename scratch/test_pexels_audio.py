import requests
import os
import subprocess

def test_pexels_audio():
    headers = {'Authorization': 'jzW35RaEfbNzE1KKdMUqklUJ1zEobNVpveL7ka1tfBY1qWUpF06T4Dto'}
    r = requests.get('https://api.pexels.com/videos/search?query=laughter&per_page=1', headers=headers)
    data = r.json()
    if not data['videos']:
        print("No videos found")
        return
    
    vid_url = data['videos'][0]['video_files'][0]['link']
    print(f"Downloading {vid_url}...")
    
    r = requests.get(vid_url, stream=True)
    with open("test_vid.mp4", "wb") as f:
        f.write(r.content)
    
    # Extract audio
    print("Extracting audio...")
    subprocess.run(["ffmpeg", "-y", "-i", "test_vid.mp4", "-vn", "-ac", "1", "test_audio.wav"], capture_output=True)
    
    if os.path.exists("test_audio.wav"):
        size = os.path.getsize("test_audio.wav")
        print(f"Success! Audio size: {size} bytes")
        # Check if it's silent
        res = subprocess.run(["ffmpeg", "-i", "test_audio.wav", "-af", "volumedetect", "-f", "null", "-"], capture_output=True, text=True)
        print(res.stderr[-500:])

if __name__ == "__main__":
    test_pexels_audio()
