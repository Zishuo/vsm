I'll help you create a basic README.md file for your project. Here's a markdown file that documents the key aspects of your video summary manager:

```markdown:README.md
# Video Summary Manager (VSM)

A Python tool for downloading, transcribing, and summarizing video/audio content from YouTube or local files.

## Features

- 🎥 Download YouTube videos or audio
- 📝 Automatic transcription using Whisper AI
- 🤖 AI-powered summarization using Deepseek or Ollama
- 📂 Batch processing of audio/video files
- 📄 Save transcriptions and summaries in multiple formats (txt, srt)

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/video-summary-manager.git
cd video-summary-manager
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up environment variables:
```bash
export DEEPSEEK_API_KEY="your_api_key_here"
```

## Usage

### Basic Commands

- Download and transcribe YouTube audio:
```bash
python vsm_main.py -a "https://www.youtube.com/watch?v=example" -p ./output
```

- Download and transcribe YouTube video:
```bash
python vsm_main.py -v "https://www.youtube.com/watch?v=example" -p ./output
```

- Transcribe local audio/video file:
```bash
python vsm_main.py -t /path/to/file.mp4
```

- Summarize text file:
```bash
python vsm_main.py -s /path/to/transcript.txt
```

- Process all audio/video files in a directory:
```bash
python vsm_main.py -r /path/to/directory
```

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

## Configuration

The tool uses the following environment variables:
- `DEEPSEEK_API_KEY` - Required for AI summarization

## Contributing

Contributions are welcome! Please open an issue or pull request for any improvements.

## License

MIT License
```

This README provides a comprehensive overview of your project. You can customize it further with additional details about your specific implementation or requirements. The markdown format makes it easy to read both in raw form and when rendered on GitHub or other platforms.
