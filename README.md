# Video Summary Manager (VSM)

A Python tool for downloading, transcribing, and summarizing video/audio content from YouTube or local files.

## Features

- 🎥 Download YouTube videos or audio
- 📝 Automatic transcription using local OpenAI Whisper, the latest large-v3-turbo
- 🤖 AI-powered summarization using OpenAI, Deepseek, Ollama, even with openwebui proxied api
- 📂 Batch processing of audio/video files
- 📄 Save transcriptions and summaries in multiple formats (txt, srt)

## Installation

1. Clone the repository:
    ```bash
    git clone https://github.com/Zishuo/vsm.git
    cd vsm
    ```

2. Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```

3. Set up environment variables:
    ```bash
    export OPENAI_API_KEY="your_api_key_here"
    export DEEPSEEK_API_KEY="your_api_key_here"
    export LLM_BASE_URL="your_llm_server_base_url_here"
    export LLM_MODEL_NAME="your_model_name_here"
    export OPENWEBUI_API_KEY="your_openwebui_api_key_here"
    ```

## Usage

### Basic Commands

- **Download YouTube audio only:**
    ```bash
    python vsm_main.py -a "https://www.youtube.com/watch?v=example" [-p ./output]
    ```

- **Download YouTube video with audio and video:**
    ```bash
    python vsm_main.py -v "https://www.youtube.com/watch?v=example" [-p ./output]
    ```

- **Transcribe local audio/video file:**
    ```bash
    python vsm_main.py -t /path/to/file.mp4
    ```

- **Summarize text file:**
    ```bash
    python vsm_main.py -s /path/to/transcript.txt
    ```

- **Directly summarize text content:**
    ```bash
    python vsm_main.py -c "your text content here"
    ```

- **Process all audio/video files in a directory recursively:**
    ```bash
    python vsm_main.py -r /path/to/directory
    ```

### Options

- `-a, --audio-url`: YouTube URL to download audio from
- `-v, --video-url`: YouTube URL to download video from (includes audio)
- `-p, --path`: Path to save downloaded files (default: ./)
- `-t, --transcribe`: Path to local audio file to transcribe
- `-s, --summary`: Path to text file to summarize
- `-c, --content`: Direct text content to summarize
- `-r, --recursive`: Process all audio/video files in directory recursively
- `-h, --help`: Show help message and exit

### Output Files

For each processed file, the tool generates:
- `.txt` - Full transcription
- `.srt` - Subtitle file
- `.takeaway.txt` - AI-generated summary

## Requirements

- Python 3.8+
- Whisper AI (large-v3-turbo model)
- yt-dlp
- OpenAI/Deepseek API key
- Optional: Ollama for local summarization
- Langdetect for language detection
- PyMuPDF for extracting text from PDFs

## Configuration

The tool uses the following environment variables:

- `OPENAI_API_KEY` - Required for accessing OpenAI API services.
- `DEEPSEEK_API_KEY` - Required for AI summarization using DeepSeek.
- `LLM_BASE_URL` - The base URL for the LLM API, e.g., OpenAI or DeepSeek.
- `LLM_MODEL_NAME` - The name of the language model to use for operations.
- `OPENWEBUI_API_KEY` - Required if using a local web UI setup.

## Contributing

Contributions are welcome! Please open an issue or pull request for any improvements.

## License

MIT License