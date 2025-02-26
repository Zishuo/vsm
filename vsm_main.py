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
from tiktoken import get_encoding
transcribe_model = None
#https://platform.openai.com/settings/organization/limits
# Update the MODEL_MAX_TOKENS to include context_window and max_output_tokens
MODEL_CONFIG = {
    "gpt-4o": {
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
    },
    "grok-2-latest": {
        "context_window": 100000,  # Example context window size
        "max_output_tokens": 10000,  # Example max output tokens
        "tpm_limit": 30000  # Example TPM limit
    }
    # Add other models and their configurations as needed
}

PROVIDER_CONFIG = {
    'openai': {
        'url': "https://api.openai.com/v1",
        'api_key_env': 'OPENAI_API_KEY',
        'model_name': 'gpt-4o'
    },
    'deepseek': {
        'url': "https://api.deepseek.com",
        'api_key_env': 'DEEPSEEK_API_KEY',
        'model_name': 'deepseek-chat'
    },
    'openwebui': {
        'url': "http://localhost:3000/api",
        'api_key_env': 'OPENWEBUI_API_KEY',
        'model_name': 'openwebui-model'  # Replace with actual model name if needed
    },
    'ollama': {
        'url': "http://host.docker.internal:11434/v1",
        'api_key_env': None,  # No API key needed for ollama
        'model_name': 'ollama-model'  # Replace with actual model name if needed
    },
    'xai': {
        'url': "https://api.x.ai/v1",
        'api_key_env': 'XAI_API_KEY',
        'model_name': 'grok-2-latest'
    },
    'anthropic': {
        'url': "https://api.anthropic.com/v1",
        'api_key_env': 'ANTHROPIC_API_KEY',
        'model_name': 'claude-3-7-sonnet-20250219'
    }
}

system_prompt = """You will be given a transcript of a conversation or speech. Your task is to summarize this transcript into a well-structured Markdown format. Here's how to approach this task:

1. First, read through the entire transcript carefully.
2. Summarize the main points of the transcript, ensuring you capture the key ideas and flow of the conversation or speech. Your summary should be comprehensive yet concise.

3. Format your summary using Markdown syntax. Use appropriate headers, bullet points, and other Markdown elements to structure the information clearly. For example:
   - Use # for main headers
   - Use ## for subheaders
   - Use bullet points (-) for lists
   - Use **bold** or *italic* for emphasis where appropriate

4. Include relevant details and numbers from the transcript. Don't generalize if specific figures or statistics are mentioned.

5. After your summary, add an "Insights" section. In this section, provide 2-3 key takeaways or analytical points about the content of the transcript. These should go beyond mere summary and offer some interpretation or highlight particularly significant aspects of the transcript.

6. Your entire response should be enclosed in <summary> tags. Within these tags, use Markdown formatting for the content.

Here's an example of how your output might be structured:

# Transcript Summary

## Main Topic

- Key point 1
- Key point 2
  - Subpoint with detail
- Key point 3

## Secondary Topic

Details about secondary topic...

## Numbers and Statistics

- Statistic 1: X%
- Statistic 2: Y million

# Insights

1. First key insight...
2. Second key insight...
3. Third key insight...


Remember to adjust the structure as needed to best fit the content of the specific transcript you're summarizing."""

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

def parse_arguments():
    """Parse command-line arguments."""
    import argparse
    parser = argparse.ArgumentParser(
        description="Video Summary Manager (vsm) - A tool for downloading, transcribing, and summarizing video/audio content",
        add_help=False
    )

    action_group = parser.add_mutually_exclusive_group()
    action_group.add_argument('-a', '--audio-url', help='YouTube URL to download audio from')
    action_group.add_argument('-v', '--video-url', help='YouTube URL to download video from')
    action_group.add_argument('-t', '--transcribe', help='Path to audio file to transcribe')
    action_group.add_argument('-s', '--summary', help='Path to text file to summarize')
    action_group.add_argument('-c', '--content', help='Direct text content to summarize')
    action_group.add_argument('-r', '--recursive', help='Process all audio/video files in directory recursively')

    parser.add_argument('-p', '--path', default='./', help='Path to save downloaded files (default: ./)')
    parser.add_argument('-h', '--help', action='help', help='Show this help message and exit')

    # Add new argument for selecting LLM service provider
    parser.add_argument('--llm-provider', choices=['openai', 'deepseek', 'openwebui', 'ollama', 'xai'], default='openai',
                        help='Select the LLM service provider to use (default: openai)')

    # Add new argument for specifying the language
    parser.add_argument('--language', default='en', help='Specify the language for summarization (default: en)')

    return parser.parse_args()

def get_llm_config(provider):
    """Get the LLM configuration based on the selected provider."""
    return PROVIDER_CONFIG.get(provider, PROVIDER_CONFIG['openai'])

def summarize_text(text):
    """Summarize the text using OpenAI's API with token limit handling."""
    args = parse_arguments()
    llm_config = get_llm_config(args.llm_provider)
    model_name = llm_config['model_name']
    language = args.language

    try:
        model_config = get_model_config(model_name)
        if model_config is None:
            return None

        client = initialize_client(llm_config)

        available_tokens = calculate_available_tokens(model_config)
        total_tokens = estimate_tokens(text, model_config)

        chunks = split_text_into_chunks(text, available_tokens, total_tokens, model_config)

        chunk_summaries = summarize_chunks(client, chunks, model_name, language, model_config)

        final_summary = generate_final_summary(client, chunk_summaries, model_name, language, model_config)

        return final_summary

    except Exception as e:
        print(f"[vsm] An error occurred: {e}")
        return None

def get_model_config(model_name):
    """Retrieve the model configuration."""
    model_config = MODEL_CONFIG.get(model_name)
    if not model_config:
        print(f"[vsm] Model '{model_name}' is not supported.")
        return None
    return model_config

def initialize_client(llm_config):
    """Initialize the OpenAI client."""
    api_key_env = llm_config['api_key_env']
    llm_base_url = llm_config['url']
    api_key = os.environ.get(api_key_env) if api_key_env else "ollama"

    if not api_key and api_key_env:
        print(f"[vsm] API key not set for provider: {llm_config['model_name']}")
        return None

    print(f"[vsm] LLM Base URL: {llm_base_url}")
    print(f"[vsm] Model Name: {llm_config['model_name']}")

    return OpenAI(api_key=api_key, base_url=llm_base_url)

def calculate_available_tokens(model_config):
    """Calculate the available tokens for input."""
    context_window = model_config["context_window"]
    max_output_tokens = model_config["max_output_tokens"]
    available_tokens = context_window - max_output_tokens
    print(f"[vsm] Context Window: {context_window} tokens")
    print(f"[vsm] Max Output Tokens: {max_output_tokens} tokens")
    print(f"[vsm] Available tokens for input: {available_tokens}")
    return available_tokens

def estimate_tokens(text, model_config):
    """Estimate the number of tokens in the input text."""
    encoding = get_encoding("cl100k_base")  # Adjust encoding as per model
    tokens = encoding.encode(text)
    total_tokens = len(tokens)
    print(f"[vsm] Total tokens in input text: {total_tokens}")
    print(f"[vsm] TPM Limit: {model_config['tpm_limit']} tokens per minute")
    return total_tokens

def split_text_into_chunks(text, available_tokens, total_tokens, model_config):
    """Split the text into chunks based on available tokens and TPM limit."""
    import math
    chunk_size = min(available_tokens, model_config['tpm_limit'] // 2)
    num_chunks = math.ceil(total_tokens / chunk_size)
    encoding = get_encoding("cl100k_base")

    chunks = []
    for i in range(num_chunks):
        start = i * chunk_size
        end = start + chunk_size
        chunk = encoding.decode(encoding.encode(text)[start:end])
        chunks.append(chunk)
        print(f"[vsm] Created chunk {i+1}/{num_chunks}")

    return chunks

def summarize_chunks(client, chunks, model_name, language, model_config):
    """Summarize each chunk of text."""
    chunk_summaries = []
    sleep_time = calculate_sleep_time(model_config, len(chunks[0]))

    for idx, chunk in enumerate(chunks):
        print(f"[vsm] Summarizing chunk {idx+1}/{len(chunks)}")
        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "user", "content": f"Make a detailed takeaway of the text in {language}, and then an insight. If there are any numbers, make sure to include them in the takeaway. Please use the MD file syntax."},
                    {"role": "user", "content": chunk}
                ],
                temperature=0.3,
                max_tokens=model_config["max_output_tokens"],
                stream=False
            )

            if not response or not hasattr(response, 'choices') or not response.choices:
                print(f"[vsm] Invalid or empty response received for chunk {idx+1}")
                print(f"[vsm] Raw response: {response}")
                continue

            chunk_summary = response.choices[0].message.content
            if not chunk_summary:
                print(f"[vsm] Empty summary received for chunk {idx+1}")
                continue

            print(f"[vsm] Chunk {idx+1} Summary:\n{chunk_summary}\n")
            chunk_summaries.append(chunk_summary)

            if idx < len(chunks) - 1:
                print(f"[vsm] Sleep time to avoid TPM limits: {sleep_time}")
                for i in range(int(sleep_time)):
                    time.sleep(1)
                    print(f"[vsm] Sleeping... {i+1}s")

        except Exception as e:
            print(f"[vsm] An error occurred while summarizing chunk {idx+1}: {e}")
            print(f"[vsm] Raw response: {response}")

    return chunk_summaries

def calculate_sleep_time(model_config, chunk_size):
    """Calculate the sleep time based on TPM limit."""
    return 60 / (model_config['tpm_limit'] / chunk_size)

def generate_final_summary(client, chunk_summaries, model_name, language, model_config):
    """Generate a final summary from the chunk summaries."""
    if not chunk_summaries:
        return None

    final_summary = "\n".join(chunk_summaries)

    if len(chunk_summaries) > 1:
        print("[vsm] Performing final summary on combined summaries")
        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": final_summary}
                ],
                temperature=0.3,
                max_tokens=model_config["max_output_tokens"],
                stream=False
            )

            if response and hasattr(response, 'choices') and response.choices:
                final_summary = response.choices[0].message.content.strip()
            else:
                print("[vsm] Final summary generation failed.")
                return None

        except Exception as e:
            print(f"[vsm] An error occurred during final summary: {e}")
            return None

    print(f"[vsm] Final Summary:\n{final_summary}")
    return final_summary

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
                    summary = summarize_text(text)

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

def process_download(args):
    """Handle download from YouTube."""
    try:
        title, description, audio_file_path = download_youtube_video(
            args.audio_url or args.video_url, args.path, video_mode=bool(args.video_url)
        )
        print(f"[vsm] Get the {audio_file_path}")
        return audio_file_path, transcribe_and_save(audio_file_path, args.audio_url or args.video_url, title, description) if audio_file_path else (None, None, None, None)
    except Exception as e:
        print(f"[vsm] Error downloading video: {str(e)}")
        sys.exit(1)

def process_transcribe(args):
    """Handle transcription of audio/video file."""
    if is_audio_or_video_file(args.transcribe):
        return transcribe_and_save(args.transcribe)
    print(f"[vsm] The file {args.transcribe} is not a valid audio or video file.")
    sys.exit(1)

def process_summary(args):
    """Handle summary extraction."""
    if is_pdf_file(args.summary):
        return extract_text_from_pdf(args.summary)
    try:
        with open(args.summary, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        print(f"[vsm] Error reading summary file: {e}")
        sys.exit(1)

def save_summary(takeaway_file, text, url, title, description):
    """Save the generated summary to a file."""
    if text:
        summary = summarize_text(text)
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
                with open(takeaway_file, 'r', encoding='utf-8') as f:
                    print(f.read())
            except Exception as e:
                print(f"[vsm] Error writing summary to file: {e}")
        else:
            print("[vsm] Summary generation failed. No summary to write.")

def main():
    """Main function to parse command-line arguments and perform actions."""
    args = parse_arguments()

    text, url, title, description = None, None, None, None
    takeaway_file = None

    if args.audio_url or args.video_url:
        audio_file_path, (text, url, title, description) = process_download(args)
        takeaway_file = os.path.splitext(audio_file_path)[0] if audio_file_path else None
    elif args.transcribe:
        text, url, title, description = process_transcribe(args)
        takeaway_file = os.path.splitext(args.transcribe)[0]
    elif args.summary:
        text = process_summary(args)
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

    save_summary(takeaway_file, text, url, title, description)

if __name__ == "__main__":
    main()