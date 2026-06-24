# Examples

Test files for verifying the pipeline.

## Usage

```bash
# Translate English demo to Chinese
python3 integration/translate_srt.py examples/demo_en.srt --to zh-CN --bilingual

# Translate Chinese demo to English
python3 integration/translate_srt.py examples/demo_zh.srt --to en

# Test StepFun converter with a transcript
echo "你好。今天天气很好。我们去散步吧。" | python3 integration/text_to_srt.py --stdin --lang zh
```

## Files

| File | Content | Duration |
|------|---------|----------|
| `demo_en.srt` | English product intro (10 cues) | ~50s |
| `demo_zh.srt` | Chinese product intro (10 cues) | ~50s |

## Expected Output

After running `python3 integration/translate_srt.py examples/demo_en.srt --to zh-CN --bilingual`:

1. Output file `demo_en.zh-CN.srt` created
2. Each cue contains both English (original) and Chinese (translated)
3. Cues end at punctuation boundaries (re-segmentation applied)
