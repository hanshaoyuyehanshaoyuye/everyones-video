# Contributing to Everyones Video

## Quick Start

```bash
git clone https://github.com/hanshaoyuyehanshaoyuye/everyones-video.git
cd everyones-video
pip install -r requirements.txt
pip install -r requirements-dev.txt
bash smoke_test.sh
```

## Ways to Contribute

| What | Where |
|------|-------|
| Report a bug | [GitHub Issues](https://github.com/hanshaoyuyehanshaoyuye/everyones-video/issues/new?template=bug.md) |
| Submit engine data | [Engine Report](https://github.com/hanshaoyuyehanshaoyuye/everyones-video/issues/new?template=engine.md) |
| Add a workflow | PR to `docs/WORKFLOWS.md` |
| Add language support | PR with test data + `lang_names` entry in `translate_srt.py` |
| Improve docs | PR to `README.md` or `docs/` |

## Before Submitting

1. Run tests: `pytest tests/ -v`
2. Run smoke test: `bash smoke_test.sh`
3. If adding a new feature, add tests and update README.md

## Code Style

- Python: standard library preferred over heavy frameworks
- Shell: POSIX-compatible, test with `set -euo pipefail`
- Docs: Chinese + English where possible
