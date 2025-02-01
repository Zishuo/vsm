#!/usr/bin/env python3
import sys
import os
import subprocess
import yt_dlp
from datetime import datetime
from whisper import available_models, load_model
from whisper.utils import get_writer
from openai import OpenAI
import ollama
import glob
import re
transcribe_model = None

def download_youtube_transcript(url, path):
    """Download the transcript of a YouTube video in SRT format using yt-dlp"""
    try:
        ydl_opts = {
            'skip_download': True,
            'writesubtitles': True,
            'writeautomaticsub': True,
            'subtitlesformat': 'srt',
            'subtitleslangs': ['en.*', 'a.*'],
            'quiet': True,
            'outtmpl': os.path.join(path, '%(title)s.%(ext)s'),
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            title = info.get('title', 'video').replace(' ', '_')
            ydl.download([url])

        file_path = os.path.join(path, f"{title}.en.srt")
        if not os.path.exists(file_path):
            file_path = os.path.join(path, f"{title}.a.en.srt")

        if os.path.exists(file_path):
            print("[vsm] Transcript downloaded successfully!")
            return file_path

        raise ValueError("No English transcripts found")
    except Exception as e:
        print(f"[vsm] An error occurred: {e}")
        return None

def is_valid_youtube_url(url):
    """Check if the URL is a valid YouTube URL"""
    youtube_regex = r'^(https?://)?(www\.)?(youtube\.com|youtu\.?be)/.+$'
    return bool(re.match(youtube_regex, url))

def download_youtube_video(url, path, video_mode=False):
    """Download the video or audio from a YouTube URL using yt-dlp"""
    if not is_valid_youtube_url(url):
        print("[vsm] Invalid YouTube URL")
        return None, None, None

    try:
        os.makedirs(path, exist_ok=True)
        base_ydl_opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best' if video_mode else 'bestaudio',
            'quiet': False,
            'postprocessors': [],
            'noplaylist': True,
            'restrictfilenames': True  # Added for filename sanitization
        }

        # First get metadata without downloading
        with yt_dlp.YoutubeDL(base_ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            title = re.sub(r'[\\/*?:"<>|]', '', info.get('title', 'video')).replace(' ', '_')
            upload_date = info.get('upload_date', '')
            description = info.get('description', '')

        # Build filename template with metadata
        file_template = f"{upload_date}_{title}.%(ext)s" if upload_date else f"{title}.%(ext)s"

        # Configure final download options
        final_ydl_opts = {
            **base_ydl_opts,
            'outtmpl': os.path.join(path, file_template),
        }

        if not video_mode:
            final_ydl_opts['postprocessors'].append({
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'wav',
                'preferredquality': '192',
            })

        # Perform actual download
        with yt_dlp.YoutubeDL(final_ydl_opts) as ydl:
            ydl.download([url])

        # Find downloaded file using the template pattern
        pattern = os.path.join(path, f"{upload_date}_{title}.*" if upload_date else f"{title}.*")
        downloaded_files = glob.glob(pattern)

        if not downloaded_files:
            raise FileNotFoundError(f"No files matching pattern: {pattern}")

        # Get most recent file matching our download pattern
        downloaded_files.sort(key=lambda x: os.path.getctime(x), reverse=True)
        final_path = downloaded_files[0]

        return title, description, final_path

    except Exception as e:
        print(f"[vsm] An error occurred during download: {str(e)}")
        print(f"[vsm] Error type: {type(e)}")
        import traceback
        traceback.print_exc()
        return None, None, None

def transcribe_audio(audio_file_path):
    """Transcribe audio using Whisper AI and translate to English."""
    global transcribe_model
    try:
        print("[vsm] Transcribing the audio file...")
        if transcribe_model is None:
            transcribe_model = load_model("large-v3-turbo")

        # Full transcription with detected or forced language
        result = transcribe_model.transcribe(
            audio_file_path,
            language="en",  # Force English
            verbose=True,
            temperature=(0.1, 0.6),
            no_speech_threshold=0.8,
        )
        return result

    except Exception as e:
        print(f"[vsm] An error occurred: {e}")
        return None


def is_audio_or_video_file(file_name):
    """Determines if a given file is an audio or video file based on its extension."""
    audio_video_extensions = {'.mp3', '.wav', '.mp4', '.m4a', '.flv', '.avi', '.mov', '.wmv', '.mkv'}
    _, ext = os.path.splitext(file_name)
    return ext.lower() in audio_video_extensions

def transcribe_and_save(file_path, url=None, title=None, description=None):
    """Transcribe a single audio/video file and save the transcript to disk."""
    path = os.path.dirname(file_path)
    filename = os.path.basename(file_path)
    filename_without_extension = os.path.splitext(filename)[0]
    print("[vsm] path:"+path)
    print("[vsm] filename:"+filename)
    try:
        result = transcribe_audio(file_path)
        text = result["text"]
        print(f"[vsm] Transcription complete:\n{text}")
        transcription_file = f"{filename_without_extension}.txt"
        with open(transcription_file, "w", encoding='utf-8') as file:
            if(url):
                file.write(f"URL: {url}\n")
            if(title):
                file.write(f"Title: {title}\n")
            if(description):
                file.write(f"Description: {description}\n")
            file.write(text)
        print(f"[vsm] Saved transcription to {transcription_file}")

        #save to srt file:
        srt_writer = get_writer("srt", path)
        srt_name = f"{filename}"
        print(f"[vsm] Saved srt to {path}/{srt_name}")
        srt_writer(result, srt_name)

        return text

    except Exception as e:
        print(f"[vsm] An error occurred while transcribing the file: {e}")



def openai_summarize_text(text, api_key):
    """Summarize the text using AI SERVICE:"""
    print("[vsm] " + api_key)
    print("[vsm] " + text)
    try:
        client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
        response = client.chat.completions.create(
            model="deepseek-reasoner",
            messages=[
                {"role": "system", "content": "Make a detailed takeaway of the text,and then an insight. If there is any sell rules, buy rules, and numbers, make sure include them in the takeaway. Please use the MD file syntax."},
                {"role": "user", "content": text}
            ],
            temperature=1,
            stream=False,
            max_tokens=8192,
        )
        return response.choices[0].message.content

    except Exception as e:
        print(f"[vsm] An error occurred: {e}")
        return None

#call ollama api to summary text
def ollama_chat_print(summary):
    print(f"[vsm] Model: {summary['model']}")
    print(f"[vsm] Created At: {summary['created_at']}")
    print(f"[vsm] Message Role: {summary['message']['role']}")
    print(f"[vsm] Content: \n{summary['message']['content']}")
    print(f"[vsm] Done Reason: {summary['done_reason']}")
    print(f"[vsm] Done: {summary['done']}")
    print(f"[vsm] Total Duration: {summary['total_duration']}")
    print(f"[vsm] Load Duration: {summary['load_duration']}")
    print(f"[vsm] Prompt Eval Count: {summary['prompt_eval_count']}")
    print(f"[vsm] Prompt Eval Duration: {summary['prompt_eval_duration']}")
    print(f"[vsm] Eval Count: {summary['eval_count']}")
    print(f"[vsm] Eval Duration: {summary['eval_duration']}")


def ollama_summarize(text):
    """Summarize text using the Ollama API."""
    prompt = "Summarize the following text into detailed key long takeaways. it also contains important info and a insight at the end: "
    chat_url = "http://localhost:11434/api/chat"
    query_url = "http://localhost:11434/api/generate"
    model = "llama3-gradient:latest"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": text}
        ],
        "stream": False
    }

    query = {
        "model": "llama3-gradient:latest",
        "prompt": prompt + text,
        "options": {
            "num_ctx": 16000
        }
    }

    headers = {
        'Content-Type': 'application/json'
    }
    response = ollama.generate(model=model, prompt=prompt+text)
    return response['response']

def traverse_and_transcribe(root_path):
    """Walk through all subfolders and transcribe audio/video files."""


    for subdir, _, files in os.walk(root_path):
        for file in files:
            if is_audio_or_video_file(file):
                print(f"[vsm] Found audio/video file: {file}")

                # Construct full file path
                file_path = os.path.join(subdir, file)

                # Transcribe file
                text = transcribe_and_save(file_path)
                #get OPEN AI key from os environment variable.
                api_key = os.environ['DEEPSEEK_API_KEY']
                summary = openai_summarize_text(text, api_key)
                with open(f"{file_path}.takeaway.txt",'w', encoding='utf-8') as file:
                    file.write(summary)

def print_usage():
    """Prints the usage instructions for the script."""
    print("Error in command line arguments.")
    print("Usage:")
    print("  python3 vsm_main.py -a <youtube-video-url> -p <path/to/save/file>")
    print("  python3 vsm_main.py -v <youtube-video-url> -p <path/to/save/file>")
    print("  python3 vsm_main.py -t <path/to/audio/file>")
    print("  python3 vsm_main.py -f <file/to/summary>")
    print("  python3 vsm_main.py -c <string/to/summary>")

def main():
    """Main function to parse command-line arguments and perform actions."""
    args = sys.argv
    url, path, text, audio_file_path, api_key = "", "./", "", "", "your-api-key"
    title, description = "", ""
    video_mode = False
    root = ""
    transcription_file = ""
    takeaway_file=""
    try:
        if "-a" in args:
            url = args[args.index("-a")+1]
        if "-v" in args:
            url = args[args.index("-v")+1]
            video_mode = True
        if "-p" in args:
            path = args[args.index("-p")+1]
        if "-t" in args:
            audio_file_path = args[args.index("-t")+1]
            takeaway_file = takeaway_file = os.path.splitext(audio_file_path)[0]
        if "-c" in args:
            text = args[args.index("-c")+1]
        if "-f" in args:
            print("open " + args[args.index("-f")+1])
            with open(args[args.index("-f")+1], 'r') as file:
                text = file.read()
            takeaway_file = os.path.splitext(file.name)[0]
        if "-r" in args:
            root = args[args.index("-r")+1]
    except:
        print_usage()



    if url and path:
        title, description, audio_file_path = download_youtube_video(url, path, video_mode)
        print(f"[vsm] Downloaded video to {path} and saved audio to {audio_file_path}")
    if audio_file_path:
        text = transcribe_and_save(audio_file_path,url,title,description)
    if text:
        #get key from os environment variable.
        api_key = os.environ['DEEPSEEK_API_KEY']
        summary = openai_summarize_text(text, api_key)
        #summary = ollama_summarize(text)
        print("[vsm] " + summary)
        if takeaway_file:
            takeaway_file = f"{takeaway_file}.takeaway.txt"
            print("[vsm] save to file:"+takeaway_file)
            with open(takeaway_file,'w', encoding='utf-8') as file:
                file.write(summary)
    if root:
        traverse_and_transcribe(root)
    else:
        print(f"[vsm] No audio file path provided.")



if __name__ == "__main__":
    main()
