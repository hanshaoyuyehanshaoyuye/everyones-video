#!/usr/bin/env python3
"""wjs-translating-subtitles 翻译入口 → 委托给 integration/translate_srt.py"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "integration"))
from translate_srt import main
if __name__ == "__main__":
    main()
