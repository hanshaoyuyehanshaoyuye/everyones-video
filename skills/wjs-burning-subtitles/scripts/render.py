#!/usr/bin/env python3
"""Burn subtitles and mix audio into a translated video.

Three composable modes (auto-detected from flags):

  1) Subtitles only — --video + --srt
     → re-encodes video with burned subs, original audio passes through.

  2) Dub only — --video + --dub
     → keeps original video stream; replaces or mixes the audio track.

  3) Full localized cut — --video + --srt + --dub
     → burns subs AND mixes dub. By default keeps original audio at low
     volume as a "bed" under the dub (set --bed-volume 0 or pass
     --no-original-audio to drop it).

Burn-in needs an ffmpeg built with libass. macOS Homebrew's stripped
ffmpeg lacks it; the script automatically downloads a static
libass-enabled build from evermeet.cx into /tmp/ff_bin/ on first use.
SHA256 verification protects against supply-chain tampering.

Usage:
  render.py --video IN.mp4 --srt SUB.srt [--dub DUB.mp4]
            [--out OUT.mp4] [styling flags] [audio flags]

Style flags (libass force_style):
  --font NAME          Fontname (default: "PingFang SC")
  --fontsize N         Fontsize in libass units (default: 12; calibrate
                       per video — 12 ≈ 30-40 actual px on 544x960)
  --color &HBBGGRR     Primary text color, ASS format (default: white)
  --outline-color X    Outline color (default: black)
  --outline-width N    Outline thickness (default: 2)
  --shadow N           Shadow depth (default: 1)
  --style outline|box  Border style (default: outline)
  --margin-h N         Left/right margin px (default: 20)
  --margin-v N         Bottom margin px (default: 40)

Audio flags:
  --bed-volume X       Original audio gain when dubbed (default: 0.18)
  --dub-volume X       Dub track gain (default: 1.0)
  --no-original-audio  Drop original audio entirely
  --audio-bitrate K    AAC bitrate kbps (default: 192)

Encoding flags:
  --crf N              x264 CRF when re-encoding video (default: 18)
  --preset NAME        x264 preset (default: medium)
  --copy-video         Skip subtitle burn-in even if --srt is given
                       (useful for dub-only output that retains scaling)
"""
import argparse, hashlib, os, re, shutil, subprocess, sys, time, urllib.request, zipfile
from pathlib import Path

EVERMEET_URL = "https://evermeet.cx/ffmpeg/getrelease/zip"
# SHA256 of the known-good evermeet.cx static ffmpeg release (universal binary).
# Update this when bumping the ffmpeg version. To obtain:
#   curl -sL https://evermeet.cx/ffmpeg/getrelease/zip | shasum -a 256
EVERMEET_SHA256 = os.environ.get(
    "EVERMEET_FFMPEG_SHA256",
    "",  # empty = skip check (set to pin a specific build)
)
STATIC_FF = Path("/tmp/ff_bin/ffmpeg")


def libass_ok(ff: str) -> bool:
    r = subprocess.run([ff, "-filters"], capture_output=True, text=True)
    return any(" subtitles " in line for line in r.stdout.splitlines())


def fetch_static_ffmpeg() -> str:
    if not os.environ.get("EVERMEET_FFMPEG_SHA256"):
        print(
            "⚠  WARNING: downloading ffmpeg binary from evermeet.cx without"
            " SHA256 verification.\n"
            "   Set EVERMEET_FFMPEG_SHA256 env var to pin a known-good build.\n"
            "   Recommended: install ffmpeg with libass via your package manager"
            " instead.\n"
            "     macOS:  brew install ffmpeg\n"
            "     Linux:  apt install ffmpeg\n"
            "     Windows: winget install ffmpeg\n",
            file=sys.stderr,
        )

    print("→ downloading libass-enabled ffmpeg from evermeet.cx…", file=sys.stderr)
    STATIC_FF.parent.mkdir(parents=True, exist_ok=True)
    z = "/tmp/ff_evermeet.zip"

    # Retry with exponential backoff (evermeet.cx can be flaky)
    last_err = None
    for attempt in range(3):
        try:
            urllib.request.urlretrieve(EVERMEET_URL, z)
            break
        except (urllib.error.URLError, OSError) as e:
            last_err = e
            if attempt < 2:
                wait = 2 ** attempt
                print(f"  download failed, retry in {wait}s…", file=sys.stderr)
                time.sleep(wait)
                continue
            raise
    else:
        raise last_err  # type: ignore[misc]

    # Verify SHA256 if pinned
    if EVERMEET_SHA256:
        with open(z, "rb") as f:
            actual = hashlib.sha256(f.read()).hexdigest()
        if actual != EVERMEET_SHA256:
            os.unlink(z)
            sys.exit(
                f"Checksum mismatch!\n"
                f"  Expected: {EVERMEET_SHA256[:16]}…\n"
                f"  Got:      {actual[:16]}…\n"
                f"  The downloaded binary may have been tampered with.\n"
                f"  Aborting for safety."
            )

    with zipfile.ZipFile(z) as zf:
        zf.extractall(STATIC_FF.parent)
    os.chmod(str(STATIC_FF), 0o755)
    os.unlink(z)

    if not libass_ok(str(STATIC_FF)):
        sys.exit("static ffmpeg also lacks libass — abort")
    return str(STATIC_FF)


def pick_ffmpeg(need_libass: bool) -> str:
    if STATIC_FF.exists():
        return str(STATIC_FF)
    sys_ff = shutil.which("ffmpeg") or "ffmpeg"
    if not need_libass:
        return sys_ff
    if libass_ok(sys_ff):
        return sys_ff
    return fetch_static_ffmpeg()


def build_force_style(a) -> str:
    # Validate all values: only allow alphanumeric, hex colors (&H...), spaces, basic punctuation
    _allowed = re.compile(r'^[A-Za-z0-9&H# ,.\-_/]+$')
    font = a.font
    color = a.color
    ocolor = a.outline_color
    for name, val in [("font", font), ("color", color), ("outline", ocolor)]:
        if not _allowed.match(val):
            sys.exit(f"render.py: --{name} contains invalid characters: {val!r}")
    border = 1 if a.style == "outline" else 3
    parts = [
        f"Fontname={a.font}",
        f"Fontsize={a.fontsize}",
        f"PrimaryColour={a.color}",
        f"OutlineColour={a.outline_color}",
        f"BorderStyle={border}",
        f"Outline={a.outline_width}",
        f"Shadow={a.shadow}",
        f"MarginL={a.margin_h}",
        f"MarginR={a.margin_h}",
        f"MarginV={a.margin_v}",
    ]
    # Escape commas for ffmpeg filter graph parser
    return ",".join(parts).replace(",", r"\,")


def parse_args():
    ap = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter,
                                  description=__doc__)
    ap.add_argument("--video", required=True)
    ap.add_argument("--srt", help="subtitle file to burn in")
    ap.add_argument("--dub", help="dub audio source (mp4/mp3/wav etc.)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--font", default="PingFang SC")
    ap.add_argument("--fontsize", type=int, default=12)
    ap.add_argument("--color", default="&H00FFFFFF")
    ap.add_argument("--outline-color", default="&H00000000")
    ap.add_argument("--outline-width", type=int, default=2)
    ap.add_argument("--shadow", type=int, default=1)
    ap.add_argument("--style", default="outline", choices=["outline","box"])
    ap.add_argument("--margin-h", type=int, default=20)
    ap.add_argument("--margin-v", type=int, default=40)
    ap.add_argument("--bed-volume", type=float, default=0.18)
    ap.add_argument("--dub-volume", type=float, default=1.0)
    ap.add_argument("--no-original-audio", action="store_true")
    ap.add_argument("--audio-bitrate", type=int, default=192)
    ap.add_argument("--crf", type=int, default=18)
    ap.add_argument("--preset", default="medium")
    ap.add_argument("--copy-video", action="store_true",
                    help="skip subtitle burn even if --srt is given")
    return ap.parse_args()


def main():
    a = parse_args()
    burn = bool(a.srt) and not a.copy_video
    ff = pick_ffmpeg(need_libass=burn)

    inputs = ["-i", a.video]
    if a.dub: inputs += ["-i", a.dub]

    filters = []
    if burn:
        style = build_force_style(a)
        # Escape path for ffmpeg filter graph (: → \:, \ → \\)
        safe_srt = a.srt.replace("\\", "\\\\").replace(":", "\\:")
        filters.append(f"[0:v]subtitles={safe_srt}:force_style='{style}'[v]")
        vmap = "[v]"
    else:
        vmap = "0:v"

    if a.dub and not a.no_original_audio:
        filters += [
            f"[0:a]volume={a.bed_volume}[orig]",
            f"[1:a]volume={a.dub_volume}[dub]",
            "[orig][dub]amix=inputs=2:duration=longest:normalize=0[a]",
        ]
        amap = "[a]"
    elif a.dub:
        filters.append(f"[1:a]volume={a.dub_volume}[a]")
        amap = "[a]"
    else:
        amap = "0:a"

    cmd = [ff, "-hide_banner", "-y", *inputs]
    if filters: cmd += ["-filter_complex", ";".join(filters)]
    cmd += ["-map", vmap, "-map", amap]
    if burn:
        cmd += ["-c:v","libx264","-crf",str(a.crf),"-preset",a.preset,"-pix_fmt","yuv420p"]
    else:
        cmd += ["-c:v","copy"]
    cmd += ["-c:a","aac","-b:a", f"{a.audio_bitrate}k", a.out]

    print(" ".join(cmd), file=sys.stderr)
    r = subprocess.run(cmd)
    sys.exit(r.returncode)


if __name__ == "__main__":
    main()
