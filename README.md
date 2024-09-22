# Video and Audio Transcription and Summarization Script

This Python script allows you to download, transcribe, and summarize audio and video files. It supports direct audio/video file transcription, downloading from YouTube, and summarization using the OpenAI and Ollama APIs.

## Features

- **Download and Transcribe Audio/Video from YouTube**
- **Transcribe Local Audio/Video Files**
- **Generate SRT Subtitles**
- **Summarize Transcriptions Using OpenAI GPT**
- **Summarize Transcriptions Using Ollama API**

## Requirements

- Python 3.x
- Required Python packages: `pytube`, `whisper`, `openai`, `ollama`

## Installation

1. Clone this repository:
    ```sh
    git clone https://github.com/github.com/Zishuo/vsm
    cd vsm
    ```

2. Install the required Python packages:
    ```sh
    pip install pytube whisper openai ollama
    ```

3. Set up your OpenAI API key:
    ```sh
    export OPENAI_API_KEY="your-openai-api-key"
    ```

## Usage

### Download and Transcribe a YouTube Video

```sh
python3 vsm_main.py -a <youtube-video-url> -p <path/to/save/file>
```

### Download and Transcribe a YouTube Video (Video Mode)

```sh
python3 vsm_main.py -v <youtube-video-url> -p <path/to/save/file>
```

### Transcribe a Local Audio/Video File

```sh
python3 vsm_main.py -t <path/to/audio/file>
```

### Summarize a Text File

```sh
python3 vsm_main.py -f <file/to/summary>
```

### Summarize a Text String

```sh
python3 vsm_main.py -c <string/to/summary>
```

### Traverse Directories and Transcribe Audio/Video Files

```sh
python3 vsm_main.py -r <root/directory/path>
```

## Example

Download and transcribe a YouTube video, then summarize the transcription:

```sh
python3 vsm_main.py -a https://www.youtube.com/watch?v=example -p ./downloads/
```

## Functions

### `is_audio_or_video_file(file_name)`

Determines if a given file is an audio or video file based on its extension.

### `transcribe_and_save(file_path, url=None, title=None, description=None)`

Transcribes a single audio/video file and saves the transcript to disk and as an SRT file.

### `download_youtube_transcript(url, path)`

Downloads the transcript of a YouTube video in SRT format.

### `download_youtube_video(url, path, video_mode=False)`

Downloads the video or audio from a YouTube URL.

### `transcribe_audio(audio_file_path)`

Transcribes audio using Whisper AI.

### `openai_summarize_text(text, api_key)`

Summarizes the text using OpenAI GPT.

### `ollama_summarize(text)`

Summarizes text using the Ollama API.

### `traverse_and_transcribe(root_path)`

Walks through all subfolders and transcribes audio/video files.

## Error Handling

The script includes error handling for various operations like downloading videos, transcribing audio, and summarizing text.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgements

- [Pytube](https://github.com/nficano/pytube)
- [OpenAI](https://openai.com)
- [Whisper](https://github.com/openai/whisper)
- [Ollama](https://github.com/ollama)

---

Feel free to customize this README to match your project's specific details and structure.
