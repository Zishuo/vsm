#!/usr/bin/env python3
import sys
import os
import subprocess
import yt_dlp
from datetime import datetime
from whisper import available_models, load_model
from whisper.utils import get_writer
from openai import OpenAI
import glob
import re
import fitz  # PyMuPDF
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
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            })

        # Check if file already exists before downloading
        pattern = os.path.join(path, f"{upload_date}_{title}.*" if upload_date else f"{title}.*")
        existing_files = glob.glob(pattern)

        if existing_files:
            print(f"[vsm] File already exists, skipping download: {existing_files[0]}")
            return title, description, existing_files[0]

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

        # Extract filename without extension for context
        filename = os.path.splitext(os.path.basename(audio_file_path))[0]

        # Full transcription with detected or forced language
        result = transcribe_model.transcribe(
            audio_file_path,
            language="en",  # Force English
            verbose=True,
            temperature=(0.0, 0.1),  # Even lower temperature for more stability
            no_speech_threshold=0.95,  # Higher threshold to better handle silence
            logprob_threshold=-0.8,  # More strict confidence threshold
            compression_ratio_threshold=2.6,  # More strict repetition detection
            condition_on_previous_text=False,
            initial_prompt=f"Transcribe the following audio clearly and accurately. Avoid repetitions and filler words. The content is about: {filename}.",
            word_timestamps=True,
            beam_size=5,  # Required for patience parameter
            patience=2.0  # More patience for long silences
        )

        if result is None:
            raise ValueError("Transcription returned no results")

        return result

    except Exception as e:
        print(f"[vsm] An error occurred: {e}")
        return None

def is_audio_or_video_file(file_name):
    """Determines if a given file is an audio or video file based on its extension."""
    audio_video_extensions = {'.mp3', '.wav', '.mp4', '.m4a', '.flv', '.avi', '.mov', '.wmv', '.mkv'}
    _, ext = os.path.splitext(file_name)
    return ext.lower() in audio_video_extensions

def is_pdf_file(file_name):
    """Check if a file is a PDF based on its extension"""
    _, ext = os.path.splitext(file_name)
    return ext.lower() == '.pdf'

def extract_text_from_pdf(pdf_path):
    """Extract text from a PDF file using PyMuPDF"""
    try:
        text = ""
        with fitz.open(pdf_path) as doc:
            for page in doc:
                text += page.get_text()
        return text
    except Exception as e:
        print(f"[vsm] Error reading PDF: {e}")
        return None

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

        # Save transcription with metadata
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

        # Save SRT file
        srt_writer = get_writer("srt", path)
        srt_name = f"{filename}"
        print(f"[vsm] Saved srt to {path}/{srt_name}")
        srt_writer(result, srt_name)

        return text, url, title, description  # Return metadata along with text

    except Exception as e:
        print(f"[vsm] An error occurred while transcribing the file: {e}")
        return None, None, None, None

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

def traverse_and_transcribe(root_path):
    """Walk through all subfolders and transcribe audio/video files."""
    for subdir, _, files in os.walk(root_path):
        for file in files:
            if is_audio_or_video_file(file):
                print(f"[vsm] Found audio/video file: {file}")
                file_path = os.path.join(subdir, file)

                # Transcribe file and get metadata
                text, url, title, description = transcribe_and_save(file_path)

                if text:
                    api_key = os.environ['DEEPSEEK_API_KEY']
                    summary = openai_summarize_text(text, api_key)

                    # Save takeaway with metadata
                    with open(f"{file_path}.takeaway.txt", 'w', encoding='utf-8') as file:
                        if url:
                            file.write(f"URL: {url}\n")
                        if title:
                            file.write(f"Title: {title}\n")
                        if description:
                            file.write(f"Description: {description}\n\n")
                        file.write(summary)

def print_usage():
    """Prints the usage instructions for the script."""
    print("Video Summary Manager (vsm) - A tool for downloading, transcribing, and summarizing video/audio content")
    print("Usage:")
    print("  vsm_main.py [options]")
    print("\nOptions:")
    print("  -a, --audio-url      YouTube URL to download audio from")
    print("  -v, --video-url      YouTube URL to download video from")
    print("  -p, --path           Path to save downloaded files (default: ./)")
    print("  -t, --transcribe     Path to audio file to transcribe")
    print("  -s, --summary        Path to text file to summarize")
    print("  -c, --content        Direct text content to summarize")
    print("  -r, --recursive      Process all audio/video files in directory recursively")
    print("  -h, --help           Show this help message and exit")

def main():
    """Main function to parse command-line arguments and perform actions."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Video Summary Manager (vsm) - A tool for downloading, transcribing, and summarizing video/audio content",
        add_help=False
    )

    # Define mutually exclusive group for main actions
    action_group = parser.add_mutually_exclusive_group()
    action_group.add_argument('-a', '--audio-url', help='YouTube URL to download audio from')
    action_group.add_argument('-v', '--video-url', help='YouTube URL to download video from')
    action_group.add_argument('-t', '--transcribe', help='Path to audio file to transcribe')
    action_group.add_argument('-s', '--summary', help='Path to text file to summarize')
    action_group.add_argument('-c', '--content', help='Direct text content to summarize')
    action_group.add_argument('-r', '--recursive', help='Process all audio/video files in directory recursively')

    # Optional arguments
    parser.add_argument('-p', '--path', default='./', help='Path to save downloaded files (default: ./)')
    parser.add_argument('-h', '--help', action='help', help='Show this help message and exit')

    try:
        args = parser.parse_args()

        # Initialize all variables to avoid reference errors
        text = None
        url = None
        title = None
        description = None
        takeaway_file = None  # Initialize takeaway_file

        if args.audio_url or args.video_url:
            try:
                title, description, audio_file_path = download_youtube_video(
                    args.audio_url or args.video_url,
                    args.path,
                    video_mode=bool(args.video_url)
                )
                print(f"[vsm] Downloaded {'video' if args.video_url else 'audio'} to {args.path}")

                if audio_file_path:
                    text, url, title, description = transcribe_and_save(
                        audio_file_path,
                        args.audio_url or args.video_url,
                        title,
                        description
                    )
                    takeaway_file = os.path.splitext(audio_file_path)[0]  # Set takeaway_file path
            except Exception as e:
                print(f"[vsm] Error downloading video: {str(e)}")
                sys.exit(1)

        elif args.transcribe:
            text, url, title, description = transcribe_and_save(args.transcribe)
            takeaway_file = os.path.splitext(args.transcribe)[0]

        elif args.summary:
            if is_pdf_file(args.summary):
                text = extract_text_from_pdf(args.summary)
            else:
                with open(args.summary, 'r', encoding='utf-8') as f:
                    text = f.read()
            takeaway_file = os.path.splitext(args.summary)[0]

        elif args.content:
            text = args.content
            takeaway_file = "summary"

        elif args.recursive:
            traverse_and_transcribe(args.recursive)
            return

        else:
            parser.print_help()
            return

        # Process summary if we have text
        if text:
            api_key = os.environ['DEEPSEEK_API_KEY']
            summary = openai_summarize_text(text, api_key)

            if takeaway_file:
                takeaway_file = f"{takeaway_file}.takeaway.txt"
                print("[vsm] Saving summary to:", takeaway_file)
                with open(takeaway_file, 'w', encoding='utf-8') as f:
                    if url:
                        f.write(f"URL: {url}\n")
                    if title:
                        f.write(f"Title: {title}\n")
                    if description:
                        f.write(f"Description: {description}\n\n")
                    f.write(summary)

                # Read and print the file content after writing
                with open(takeaway_file, 'r', encoding='utf-8') as f:
                    print(f.read())

    except Exception as e:
        print(f"[vsm] Error: {str(e)}")
        sys.exit(1)



if __name__ == "__main__":
    main()
