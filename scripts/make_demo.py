"""Generate a terminal-demo GIF for the everyones-video README."""
from PIL import Image, ImageDraw, ImageFont
import os

W, H = 740, 420
PAD = 18
LINE_H = 15
FONT_SIZE = 12

BG = (26, 27, 38)
GREEN = (158, 206, 106)
CYAN = (125, 207, 255)
YELLOW = (224, 175, 104)
DIM = (169, 177, 214)
WHITE = (192, 202, 245)
PROMPT_COLOR = (65, 166, 87)

CMD = 'bash pipeline.sh "tutorial.mp4" --translate --dub --burn'

# Each scene: (lines, hold_for_N_frames)
# Lines keep adding; the prompt fades to dim after command runs
SCENES = [
    # 0: empty terminal
    ([], 4),
    # 1-3: typing the command (one char chunk per frame)
    *[([(CMD[:k], WHITE)], 1) for k in range(0, len(CMD) + 1, 3)],
    # 4: command entered, pause
    ([(CMD, GREEN)], 6),
    # 5: banner
    ([(CMD, DIM), ("", (0,0,0)), ("═══ Everyones Video Pipeline ═══", CYAN),
      ("  Language: en  |  ASR: auto  |  Translate: zh-CN  |  Dub + Burn", DIM)], 8),
    # 6: subtitle check
    ([(CMD, DIM), ("", (0,0,0)), ("═══ Everyones Video Pipeline ═══", CYAN),
      ("", (0,0,0)), ("══ Step 1: Extract + Subtitle Check ══", YELLOW)], 5),
    # 7: found captions
    ([(CMD, DIM), ("", (0,0,0)), ("═══ Everyones Video Pipeline ═══", CYAN),
      ("", (0,0,0)), ("══ Step 1: Extract + Subtitle Check ══", YELLOW),
      ("  → Found YouTube auto-captions!", GREEN),
      ("  🎯 142 cues — skipping ASR, saving ~$0.15", GREEN)], 8),
    # 8: skipped steps
    ([(CMD, DIM), ("", (0,0,0)), ("═══ Everyones Video Pipeline ═══", CYAN),
      ("", (0,0,0)), ("══ Step 1 ══ ✓ Found captions (142 cues)", GREEN),
      ("══ Step 2 ══ ✓ ASR skipped", DIM),
      ("══ Step 3 ══ ✓ Text→SRT skipped", DIM)], 5),
    # 9: translate
    ([(CMD, DIM), ("", (0,0,0)), ("═══ Everyones Video Pipeline ═══", CYAN),
      ("", (0,0,0)), ("══ Step 1 ══ ✓ Found captions (142 cues)", GREEN),
      ("══ Step 2 ══ ✓ ASR skipped", DIM),
      ("══ Step 3 ══ ✓ Text→SRT skipped", DIM),
      ("", (0,0,0)), ("══ Step 4: Translate (en → zh-CN) ══", YELLOW),
      ("  → DeepSeek: 142 cues ...", DIM)], 4),
    # 10: translate done
    ([(CMD, DIM), ("", (0,0,0)), ("═══ Everyones Video Pipeline ═══", CYAN),
      ("", (0,0,0)), ("══ Step 1 ══ ✓ Found captions (142 cues)", GREEN),
      ("══ Step 2 ══ ✓ ASR skipped", DIM),
      ("══ Step 3 ══ ✓ Text→SRT skipped", DIM),
      ("", (0,0,0)), ("══ Step 4: Translate (en → zh-CN) ══", YELLOW),
      ("  ✓ 142 cues → subtitles.zh-CN.srt (bilingual)", GREEN)], 8),
    # 11: TTS
    ([(CMD, DIM), ("", (0,0,0)), ("═══ Everyones Video Pipeline ═══", CYAN),
      ("", (0,0,0)), ("  ...", DIM),
      ("", (0,0,0)), ("══ Step 4 ══ ✓ subtitles.zh-CN.srt", GREEN),
      ("", (0,0,0)), ("══ Step 5: TTS Dubbing ══", YELLOW),
      ("  → Edge-TTS: 142 segments, voice zh-CN-XiaoxiaoNeural", DIM)], 4),
    # 12: TTS done
    ([(CMD, DIM), ("", (0,0,0)), ("═══ Everyones Video Pipeline ═══", CYAN),
      ("", (0,0,0)), ("  ...", DIM),
      ("", (0,0,0)), ("══ Step 4 ══ ✓ subtitles.zh-CN.srt", GREEN),
      ("", (0,0,0)), ("══ Step 5: TTS Dubbing ══", YELLOW),
      ("  ✓ dub.mp3 (2.3 MB)", GREEN)], 5),
    # 13: burn
    ([(CMD, DIM), ("", (0,0,0)), ("═══ Everyones Video Pipeline ═══", CYAN),
      ("", (0,0,0)), ("  ...", DIM),
      ("", (0,0,0)), ("══ Step 5 ══ ✓ dub.mp3", GREEN),
      ("", (0,0,0)), ("══ Step 6: Burn Subtitles ══", YELLOW),
      ("  → libass hard-sub + audio mix ...", DIM)], 3),
    # 14: burn done
    ([(CMD, DIM), ("", (0,0,0)), ("═══ Everyones Video Pipeline ═══", CYAN),
      ("", (0,0,0)), ("  ...", DIM),
      ("", (0,0,0)), ("══ Step 5 ══ ✓ dub.mp3", GREEN),
      ("", (0,0,0)), ("══ Step 6: Burn Subtitles ══", YELLOW),
      ("  ✓ tutorial_subtitled.mp4 (48 MB)", GREEN)], 5),
    # 15: DONE
    ([(CMD, DIM), ("", (0,0,0)), ("═══ Everyones Video Pipeline ═══", CYAN),
      ("", (0,0,0)), ("  ...", DIM),
      ("  ✓ tutorial_subtitled.mp4", GREEN),
      ("", (0,0,0)), ("══════════", CYAN),
      ("  Done!  |  Time: 23s  |  Cost: ¥0.00", WHITE)], 15),
]

# Find font
font = None
for fp in [
    "C:/Windows/Fonts/consola.ttf",
    "C:/Windows/Fonts/cour.ttf",
    "C:/Windows/Fonts/lucon.ttf",
    "/usr/share/fonts/TTF/DejaVuSansMono.ttf",
]:
    try:
        font = ImageFont.truetype(fp, FONT_SIZE)
        break
    except Exception:
        continue
if font is None:
    font = ImageFont.load_default()


def render():
    out_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs")
    os.makedirs(out_dir, exist_ok=True)

    frames = []
    for lines, hold in SCENES:
        for _ in range(hold):
            img = Image.new("RGBA", (W, H), BG)
            draw = ImageDraw.Draw(img)

            # Terminal chrome — traffic lights
            for cx, ccol in [(20, (237, 108, 94)), (32, (235, 182, 70)), (44, (135, 190, 114))]:
                draw.ellipse([(cx, 10), (cx + 8, 18)], fill=ccol)

            # Title bar
            draw.text((58, 9), "everyones-video ~ bash", fill=(86, 95, 137), font=font)

            # Content lines
            for j, (text, color) in enumerate(lines):
                y = 38 + j * LINE_H
                if y > H - PAD:
                    break
                draw.text((PAD, y), text, fill=color, font=font)

            frames.append(img.convert("P", palette=Image.Palette.ADAPTIVE))

    # Duplicate last frame for pause
    frames.append(frames[-1].copy())

    out_path = os.path.join(out_dir, "demo.gif")
    frames[0].save(
        out_path,
        save_all=True,
        append_images=frames[1:],
        duration=80,  # 80ms per frame = ~12.5 fps, smooth enough
        loop=0,
        optimize=True,
        disposal=2,
    )
    duration_s = len(frames) * 0.08
    size_kb = os.path.getsize(out_path) / 1024
    print(f"GIF: {out_path}")
    print(f"Frames: {len(frames)} | Duration: {duration_s:.1f}s | Size: {size_kb:.0f} KB")


if __name__ == "__main__":
    render()
