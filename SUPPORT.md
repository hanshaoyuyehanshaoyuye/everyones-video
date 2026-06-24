# Support

## Getting Help

### Documentation

- **[README.md](README.md)** — Overview, quick start, engine comparison
- **[docs/WORKFLOWS.md](docs/WORKFLOWS.md)** — 9 workflow scenarios
- **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** — Architecture decision records
- **[docs/OPTIMIZATION.md](docs/OPTIMIZATION.md)** — Cost-saving strategies
- **[docs/ASR_COMPARISON.md](docs/ASR_COMPARISON.md)** — 6-engine deep comparison

### Troubleshooting

1. **"pipeline.sh: command not found"** — Ensure you're in the project root: `cd everyones-video`
2. **"FunASR not installed"** — Run `pip install -r requirements-full.txt` (first run downloads ~1GB model)
3. **"ffmpeg: libass not found"** — macOS: `brew install ffmpeg`. Linux: `apt install ffmpeg`. The script will auto-download a static build as fallback.
4. **"DEEPSEEK_API_KEY not set"** — Get a key at [platform.deepseek.com](https://platform.deepseek.com), or install [Ollama](https://ollama.com) for local translation.
5. **"No subtitles found"** — The YouTube video may not have auto-captions. Try `--engine funasr` (Chinese) or `--engine faster-whisper` (English).

### Still stuck?

Open a [GitHub Issue](https://github.com/hanshaoyuyehanshaoyuye/everyones-video/issues) with:

- Your OS and Python version (`python3 --version`)
- The full command you ran
- The error output (first 20 lines)
- Whether you're using Docker or local install
