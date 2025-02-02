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
import time
from langdetect import detect
transcribe_model = None
#https://platform.openai.com/settings/organization/limits
# Update the MODEL_MAX_TOKENS to include context_window and max_output_tokens
MODEL_CONFIG = {
    "gpt-3.5-turbo": {
        "context_window": 4096,
        "max_output_tokens": 2048,
        "tpm_limit": 30000  # Example TPM limit
    },
    "gpt-4o": {
        "context_window": 128000,
        "max_output_tokens": 16384,
        "tpm_limit": 30000  # Example TPM limit
    },
    "gpt-4o-2024-11-20": {
        "context_window": 128000,
        "max_output_tokens": 16384,
        "tpm_limit": 30000  # Example TPM limit
    },
    "gpt-4o-2024-08-06": {
        "context_window": 128000,
        "max_output_tokens": 16384,
        "tpm_limit": 30000  # Example TPM limit
    },
    "gpt-4o-2024-05-13": {
        "context_window": 128000,
        "max_output_tokens": 4096,
        "tpm_limit": 30000  # Example TPM limit
    },
    "chatgpt-4o-latest": {
        "context_window": 128000,
        "max_output_tokens": 16384,
        "tpm_limit": 30000  # Example TPM limit
    },
#https://api-docs.deepseek.com/quick_start/pricing
    "deepseek-reasoner": {
        "context_window": 64000,
        "max_output_tokens": 8000,
        "tpm_limit": 30000  # Example TPM limit
    },
    "deepseek-chat": {
        "context_window": 64000,
        "max_output_tokens": 8000,
        "tpm_limit": 30000  # Example TPM limit
    },
    "deepseek-r1:32b": {
        "context_window": 10000,
        "max_output_tokens": 800,
        "tpm_limit": 0xFFFFFFFF  # Example TPM limit
    }
    # Add other models and their configurations as needed
}

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

        # Check if file already exists before downloading
        pattern = os.path.join(path, f"{upload_date}_{title}.*" if upload_date else f"{title}.*")
        downloaded_files = glob.glob(pattern)

        if not downloaded_files:
            # Retry with a more generic pattern if no files found
            pattern = os.path.join(path, f"*{info['id']}*.*")
            downloaded_files = glob.glob(pattern)

        # Filter out non-video/audio files (e.g., .txt files)
        downloaded_files = [f for f in downloaded_files if is_audio_or_video_file(f)]

        if downloaded_files:
            # If files are found, return the most recent one
            downloaded_files.sort(key=lambda x: os.path.getctime(x), reverse=True)
            final_path = downloaded_files[0]
            print(f"[vsm] Found existing file: {final_path}")
            return title, description, final_path

        # Perform actual download if no existing file is found
        with yt_dlp.YoutubeDL(base_ydl_opts) as ydl:
            ydl.download([url])

        # Re-check for downloaded files
        downloaded_files = glob.glob(pattern)
        downloaded_files = [f for f in downloaded_files if is_audio_or_video_file(f)]

        if not downloaded_files:
            raise FileNotFoundError("No valid audio/video files found after download.")

        # Get most recent file matching our download pattern
        downloaded_files.sort(key=lambda x: os.path.getctime(x), reverse=True)
        final_path = downloaded_files[0]

        return title, description, final_path

    except Exception as e:
        print(f"[vsm] An error occurred during download: {str(e)}")
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
            #language="en",  # Force English
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
    audio_video_extensions = {'.mp3', '.wav', '.mp4', '.m4a', '.flv', '.avi', '.mov', '.wmv', '.mkv', '.webm'}
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
    if not is_audio_or_video_file(file_path):
        print(f"[vsm] The file {file_path} is not a valid audio or video file.")
        return None, None, None, None

    path = os.path.dirname(file_path)
    filename = os.path.basename(file_path)
    filename_without_extension = os.path.splitext(filename)[0]
    print("[vsm] path:" + path)
    print("[vsm] filename:" + filename)
    try:
        result = transcribe_audio(file_path)
        if result is None:
            return None, None, None, None

        text = result["text"]
        print(f"[vsm] Transcription complete:\n{text}")

        # Save transcription with metadata
        transcription_file = f"{filename_without_extension}.txt"
        with open(transcription_file, "w", encoding='utf-8') as file:
            if url:
                file.write(f"URL: {url}\n")
            if title:
                file.write(f"Title: {title}\n")
            if description:
                file.write(f"Description: {description}\n")
            file.write(text)
        print(f"[vsm] Saved transcription to {transcription_file}")

        # Save SRT file
        srt_writer = get_writer("srt", path)
        srt_name = f"{filename_without_extension}.srt"
        print(f"[vsm] Saved srt to {path}/{srt_name}")
        srt_writer(result, srt_name)

        return text, url, title, description  # Return metadata along with text

    except Exception as e:
        print(f"[vsm] An error occurred while transcribing the file: {e}")
        return None, None, None, None

def openai_summarize_text(text):
    """Summarize the text using OpenAI's API with token limit handling."""
    import math
    from tiktoken import get_encoding

    # Detect the language of the input text
    try:
        language = detect(text)
        print(f"[vsm] Detected language: {language}")
    except Exception as e:
        print(f"[vsm] Language detection failed: {e}")
        language = 'en'  # Default to English if detection fails

    # Retrieve environment variables DEEPSEEK_API_KEY/OPENAI_API_KEY/GOOGLE_API_KEY/OPENWEBUI_API_KEY depending on the LLM_BASE_URL
    llm_base_url = os.environ.get('LLM_BASE_URL', "https://api.openai.com")  # Default to OpenAI's URL
    print(f"[vsm] LLM Base URL: {llm_base_url}")
    if llm_base_url == "https://api.deepseek.com":
        api_key = os.environ.get('DEEPSEEK_API_KEY')
    elif llm_base_url == "https://api.openai.com":
        print("[vsm] OPENAI_API_KEY: "+os.environ.get('OPENAI_API_KEY'))
        api_key = os.environ.get('OPENAI_API_KEY')
    elif llm_base_url == "http://localhost:3000/api":
        api_key = os.environ.get('OPENWEBUI_API_KEY')
    elif llm_base_url == "http://host.docker.internal:11434/v1":
        api_key = "ollama"
    else:
        print("[vsm] No valid API key found.")
        return None

    if not api_key and llm_base_url != "http://host.docker.internal:11434/v1":
        print(f"[vsm] API key not set for base URL: {llm_base_url}")
        return None

    model_name = os.environ.get('LLM_MODEL_NAME', "gpt-4o")  # Default to a standard OpenAI model

    print(f"[vsm] Model Name: {model_name}")

    # Get model configuration
    model_config = MODEL_CONFIG.get(model_name)
    if not model_config:
        print(f"[vsm] Model '{model_name}' is not supported.")
        return None

    context_window = model_config["context_window"]
    max_output_tokens = model_config["max_output_tokens"]
    tpm_limit = model_config["tpm_limit"]  # Retrieve TPM limit

    print(f"[vsm] Context Window: {context_window} tokens")
    print(f"[vsm] Max Output Tokens: {max_output_tokens} tokens")
    print(f"[vsm] TPM Limit: {tpm_limit} tokens per minute")

    client = OpenAI(api_key=api_key, base_url=llm_base_url)  # Ensure you're using openai>=1.0.0

    try:
        # Define max_tokens based on model's context window and max output tokens
        available_tokens = context_window - max_output_tokens
        print(f"[vsm] Available tokens for input: {available_tokens}")

        # Estimate tokens in the input text
        encoding = get_encoding("cl100k_base")  # Adjust encoding as per model
        tokens = encoding.encode(text)
        total_tokens = len(tokens)
        print(f"[vsm] Total tokens in input text: {total_tokens}")

        # Adjust chunk size to be smaller to fit within TPM limits
        chunk_size = min(available_tokens, tpm_limit // 2)  # Ensure chunk size is within TPM
        num_chunks = math.ceil(total_tokens / chunk_size)
        summaries = []

        # Calculate sleep time based on TPM limit
        sleep_time = 60 / (tpm_limit / chunk_size)  # Calculate sleep time to not exceed TPM

        for i in range(num_chunks):
            start = i * chunk_size
            end = start + chunk_size
            chunk = encoding.decode(tokens[start:end])
            summaries.append(chunk)
            print(f"[vsm] Created chunk {i+1}/{num_chunks}")

        # Summarize each chunk
        final_summary = ""
        for idx, chunk in enumerate(summaries):
            print(f"[vsm] Summarizing chunk {idx+1}/{len(summaries)}")
            response = None  # Initialize response variable
            try:
                response = client.chat.completions.create(
                    model=model_name,  # Specify the model here
                    messages=[
                        {"role": "user", "content": f"Make a detailed takeaway of the text in {language}, and then an insight. If there are any numbers, make sure to include them in the takeaway. Please use the MD file syntax."},
                        {"role": "user", "content": chunk}
                    ],
                    temperature=0.3,
                    max_tokens=max_output_tokens,
                    stream=False
                )

                # Check if response is valid
                if not response or not hasattr(response, 'choices') or not response.choices:
                    print(f"[vsm] Invalid or empty response received for chunk {idx+1}")
                    print(f"[vsm] Raw response: {response}")
                    continue

                chunk_summary = response.choices[0].message.content
                if not chunk_summary:
                    print(f"[vsm] Empty summary received for chunk {idx+1}")
                    continue

                # Print each chunk summary
                print(f"[vsm] Chunk {idx+1} Summary:\n{chunk_summary}\n")

                final_summary += chunk_summary + "\n"
                #if this is not the last chunk, introduce a delay to avoid exceeding TPM limits
                if idx < num_chunks - 1:
                    print(f"[vsm] Sleep time to avoid TPM limits: {sleep_time}")
                    # Introduce a delay to avoid exceeding TPM limits
                    for i in range(int(sleep_time)):
                        time.sleep(1)
                        print(f"[vsm] Sleeping... {i+1}s")   # Print sleep progress each second

            except Exception as e:
                print(f"[vsm] An error occurred while summarizing chunk {idx+1}: {e}")
                # Print the raw response for debugging
                print(f"[vsm] Raw response: {response}")
                continue

        # Perform a final summary on the combined summaries if more than one chunk
        if final_summary and num_chunks > 1:
            print("[vsm] Performing final summary on combined summaries")
            try:
                response = client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "user", "content": f"Summarize the following text in {language}, please keep the details as much as possible."},
                        {"role": "user", "content": final_summary}
                    ],
                    temperature=0.3,
                    max_tokens=max_output_tokens,
                    stream=False
                )

                if response and hasattr(response, 'choices') and response.choices:
                    final_summary = response.choices[0].message.content.strip()
                else:
                    print("[vsm] Final summary generation failed.")
                    final_summary = None

            except Exception as e:
                print(f"[vsm] An error occurred during final summary: {e}")
                final_summary = None

            # Print the final summary
            if final_summary:
                print(f"[vsm] Final Summary:\n{final_summary}")

        return final_summary

    except Exception as e:
        print(f"[vsm] An error occurred: {e}")
        return None

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
                    summary = openai_summarize_text(text)

                    if summary:
                        # Save takeaway with metadata
                        with open(f"{file_path}.takeaway.txt", 'w', encoding='utf-8') as file_obj:
                            if url:
                                file_obj.write(f"URL: {url}\n")
                            if title:
                                file_obj.write(f"Title: {title}\n")
                            if description:
                                file_obj.write(f"Description: {description}\n\n")
                            file_obj.write(summary)
                        print(f"[vsm] Saved summary to {file_path}.takeaway.txt")

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
                print(f"[vsm] Get the {audio_file_path}")

                if audio_file_path and is_audio_or_video_file(audio_file_path):
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
            if is_audio_or_video_file(args.transcribe):
                text, url, title, description = transcribe_and_save(args.transcribe)
                takeaway_file = os.path.splitext(args.transcribe)[0]
            else:
                print(f"[vsm] The file {args.transcribe} is not a valid audio or video file.")
                sys.exit(1)

        elif args.summary:
            if is_pdf_file(args.summary):
                text = extract_text_from_pdf(args.summary)
            else:
                try:
                    with open(args.summary, 'r', encoding='utf-8') as f:
                        text = f.read()
                except Exception as e:
                    print(f"[vsm] Error reading summary file: {e}")
                    sys.exit(1)
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
            summary = openai_summarize_text(text)

            if summary:
                takeaway_file = f"{takeaway_file}.takeaway.txt"
                print("[vsm] Saving summary to:", takeaway_file)
                try:
                    with open(takeaway_file, 'w', encoding='utf-8') as f:
                        if url:
                            f.write(f"URL: {url}\n")
                        if title:
                            f.write(f"Title: {title}\n")
                        if description:
                            f.write(f"Description: {description}\n\n")
                        f.write(summary)
                    print(f"[vsm] Summary saved to {takeaway_file}")

                    # Read and print the file content after writing
                    with open(takeaway_file, 'r', encoding='utf-8') as f:
                        print(f.read())
                except Exception as e:
                    print(f"[vsm] Error writing summary to file: {e}")
            else:
                print("[vsm] Summary generation failed. No summary to write.")

    except Exception as e:
        print(f"[vsm] Error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
