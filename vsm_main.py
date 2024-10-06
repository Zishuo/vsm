#!/usr/bin/env python3
import sys
import os
import subprocess
from pytube import YouTube
from whisper import available_models, load_model
from whisper.utils import get_writer
from openai import OpenAI
import ollama
transcribe_model = None

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
    print("path:"+path)
    print("filename:"+filename)
    try:
        result = transcribe_audio(file_path)
        text = result["text"]
        print(f"Transcription complete:\n{text}")
        transcription_file = f"{filename_without_extension}.txt"
        with open(transcription_file, "w", encoding='utf-8') as file:
            if(url):
                file.write(f"URL: {url}\n")
            if(title):
                file.write(f"Title: {title}\n")
            if(description):
                file.write(f"Description: {description}\n")
            file.write(text)
        print(f"Saved transcription to {transcription_file}")

        #save to srt file:
        srt_writer = get_writer("srt", path)
        srt_name = f"{filename}"
        print(f"Saved srt to {path}/{srt_name}")
        srt_writer(result, srt_name)

        return text

    except Exception as e:
        print(f"An error occurred while transcribing the file: {e}")





def download_youtube_transcript(url, path):
    """Download the transcript of a YouTube video in SRT format."""
    try:
        video = YouTube(url)
        transcript_list = video.captions.all()
        if not transcript_list:
            raise ValueError("No transcripts found")

        transcript = video.captions.get_by_language_code(transcript_list[0].code)
        if not transcript:
            raise ValueError("Transcript not found for the specified language")

        transcript_srt = transcript.generate_srt_captions()
        file_path = f"{path}/{video.title.replace(' ', '_')}.srt"
        with open(file_path, 'w') as f:
            f.write(transcript_srt)
        print("Transcript downloaded successfully!")
        return file_path
    except Exception as e:
        print(f"An error occurred: {e}")
        return None

def download_youtube_video(url, path, video_mode=False):
    """Download the video or audio from a YouTube URL."""
    try:
        video = YouTube(url)
        print(f"Title: {video.title}")
        print(f"Description: {video.description}")

        file_name = f"{video.publish_date.date()}-{video.title.replace(' ', '_')}"
        if video_mode:
            stream = video.streams.get_highest_resolution()
            file_extension = "mp4"
        else:
            stream = video.streams.get_audio_only()
            file_extension = "wav"

        final_path = f"{path}/{file_name}.{file_extension}"
        stream.download(path, f"{file_name}.{file_extension}")
        print(f"{'Video' if video_mode else 'Audio'} downloaded successfully!")

        return video.title, video.description, final_path

    except Exception as e:
        print(f"An error occurred: {e}")
        return None, None, None

def transcribe_audio(audio_file_path):
    """Transcribe audio using Whisper AI."""
    global transcribe_model
    try:
        print("Transcribing the audio file...")
        if transcribe_model is None:
            transcribe_model = load_model("medium.en")
        result = transcribe_model.transcribe(audio_file_path, verbose=True, temperature=0.2, no_speech_threshold=0.2, word_timestamps=True, hallucination_silence_threshold=1)
        return result

    except Exception as e:
        print(f"An error occurred: {e}")
        return None

def openai_summarize_text(text, api_key):
    """Summarize the text using OpenAI GPT."""
    try:
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Make a detailed takeaway of the text,and then an insight. If there is any sell rules, buy rules, and numbers, make sure include them in the takeaway. Please use the MD file syntax."},
                {"role": "user", "content": text}
            ],
            temperature=1,
            max_tokens=4096
        )
        return response.choices[0].message.content

    except Exception as e:
        print(f"An error occurred: {e}")
        return None

#call ollama api to summary text
def ollama_chat_print(summary):
    print(f"Model: {summary['model']}")
    print(f"Created At: {summary['created_at']}")
    print(f"Message Role: {summary['message']['role']}")
    print(f"Content: \n{summary['message']['content']}")
    print(f"Done Reason: {summary['done_reason']}")
    print(f"Done: {summary['done']}")
    print(f"Total Duration: {summary['total_duration']}")
    print(f"Load Duration: {summary['load_duration']}")
    print(f"Prompt Eval Count: {summary['prompt_eval_count']}")
    print(f"Prompt Eval Duration: {summary['prompt_eval_duration']}")
    print(f"Eval Count: {summary['eval_count']}")
    print(f"Eval Duration: {summary['eval_duration']}")


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
                print(f"Found audio/video file: {file}")

                # Construct full file path
                file_path = os.path.join(subdir, file)

                # Transcribe file
                text = transcribe_and_save(file_path)
                #get OPEN AI key from os environment variable.
                api_key = os.environ['OPENAI_API_KEY']
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
        print(f"Downloaded video to {path} and saved audio to {audio_file_path}")
    if audio_file_path:
        text = transcribe_and_save(audio_file_path,url,title,description)
    if text:
        #get OPEN AI key from os environment variable.
        api_key = os.environ['OPENAI_API_KEY']
        summary = openai_summarize_text(text, api_key)
        #summary = ollama_summarize(text)
        print(summary)
        if takeaway_file:
            takeaway_file = f"{takeaway_file}.takeaway.txt"
            print("save to file:"+takeaway_file)
            with open(takeaway_file,'w', encoding='utf-8') as file:
                file.write(summary)
    if root:
        traverse_and_transcribe(root)
    else:
        print(f"No audio file path provided.")



if __name__ == "__main__":
    main()