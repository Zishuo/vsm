#!/usr/bin/env python3
import sys
import subprocess
import whisper
from openai import OpenAI
from pytube import YouTube
from whisper.utils import get_writer


def download_youtube_transcript(url, path):
    #download transcript
    video = YouTube(url)
    l_list = video.captions.all()
    print(l_list)
    print(l_list[0].code)
    transcript = video.captions.get_by_language_code(l_list[0].code)
    if transcript:
        # Generate SRT captions
        transcript_srt = transcript.generate_srt_captions()
        # Write the transcript to a file
        with open(f"{path}/{video.title}.srt", 'w') as f:
            f.write(transcript_srt)
        # with open(f"{path}/{video.title}.xml", 'w') as f:
        #     f.write(transcript.xml_captions)
        print("Audio and transcript downloaded successfully!")
        return f"{path}/{video.title}.srt"
    else:
        print("Transcript not found for the specified language.")
        return None



def download_youtube_video(url, path, v=False):
    try:

        # # Create a YouTube object
        clip = YouTube(url)
        print(clip.title)
        print(clip.description)
        name = ""
        # # Get the video with the highest resolution
        if v:
            print("Downloading the best video")
            video_hr = clip.streams.get_highest_resolution()

        # # Set the output path and filename
            name = f"{clip.publish_date.date()}-{clip.title}.mp4"
            name = name.replace(" ", "_")
        # # Download the video to the specified path and filename
            video_hr.download(path, name)
            print("Video downloaded successfully!")

        else:
            print("Downloading the audio")
            audio = clip.streams.get_audio_only()
            # Set the output path and filename,include the title of the video and the date
            name = f"{clip.publish_date.date()}-{clip.title}.wav"
            #replace the spaces with underscores
            name = name.replace(" ", "_")
            audio.download(path, name)
            print("Audio downloaded successfully!")

    except Exception as e:
        print(f"An error occurred: {e}")

    return clip.title, clip.description, f"{path}/{name}"



def transcribe_audio(audio_file_path):

    #use whisper to transcribe the audio
    print("Transcribing the audio file")
    print(audio_file_path)
    print(whisper.available_models())
    model = whisper.load_model("large-v2")

    #save the transcribed text to a file
    #save the tts to a file
    #set language to English
    result = model.transcribe(audio_file_path, language="en", verbose=True)


    return result

def summarize_text(text):
    #the text to summarize could be very very long, so we need to split it into multiple parts
    #and then summarize each part
    #use chat gpt to summarize the text
    client = OpenAI(api_key="sk-proj-ly9CAM2lghMAUhXzvvOgT3BlbkFJfzajVO4fdUqQk2wJ2HRH")
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "Make a detailed takeaway of the text in  original language, probably English or Chinese."},
            {"role": "user", "content": text}
        ],
        temperature=1,
        max_tokens=4096,
        top_p=1,
        frequency_penalty=0,
        presence_penalty=0
        )
    return response.choices[0].message.content

if __name__ == "__main__":
    # Get the string from the command line arguments
    #parse -a option to get the youtube video
    #parse -c option to get the text from command line
    #parse -f option to get the text from a file
    #parse -t option to transcribe the audio
    #parse -v option to get the video from the youtube
    text = ""
    path = "./"
    audio_file_path = ""
    url = ""
    title = ""
    desciption = ""
    v = False

    if "-a" in sys.argv:
        url = sys.argv[sys.argv.index("-y")+1]
    elif "-v" in sys.argv:
        url = sys.argv[sys.argv.index("-v")+1]
        v = True
    elif "-p" in sys.argv:
        path = sys.argv[sys.argv.index("-p")+1]
    elif "-c" in sys.argv:
        text = sys.argv[sys.argv.index("-c")+1]
    elif "-f" in sys.argv:
        with open(sys.argv[sys.argv.index("-f")+1], 'r') as f:
            text = f.read()
    elif "-t" in sys.argv:
        audio_file_path = sys.argv[sys.argv.index("-t")+1]
    else:
        print(url)
        print(audio_file_path)
        print(path)
        print(text)
        sys.exit(1)
    if url != "" and path != "":
        # Call the download_youtube_transcript function
        # the out put is the path to the transcript file and vedio title
        title, desciption, audio_file_path = download_youtube_video(url, path, v)

    if audio_file_path != "":
        # Call the transcribe_audio function
        result = transcribe_audio(audio_file_path)
        text = result["text"]
        print("Transcription complete!")
        print(text)
        #save to the file:
        txt_name = f"{audio_file_path}.txt"
        with open(txt_name, 'w', encoding='utf-8') as f:
            f.write(url)
            f.write(desciption)
            f.write(text)
        #save to srt file:
        srt_writer = get_writer("srt", path)
        srt_name = f"{audio_file_path}.srt"
        srt_writer(result, srt_name)


    if text != "":
        # Call the summarize_text function
        summary = summarize_text(text)
            #save the summary to a file
        with open(f"{audio_file_path}.takeaway.txt", 'w', encoding='utf-8') as f:
            f.write(summary)
        print("Summary complete!")
        print(summary)