"""Builds the launch video from the real takes in demo/raw/, the Cartesia narration in vo/ and the overlays in build/overlays/.

    python3 demo/launch-video/build.py            # writes countersign-launch.mp4 and countersign-30s.mp4

Every shot is a recording of the running app; the call audio is the real call. Nothing is generated except the narration (Cartesia)
and the two title cards. See timeline.json for the cut and script.md for the numbers and their sources.
"""

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE.parent / "raw"
BUILD = HERE / "build"
OV = BUILD / "overlays"
FPS = 30
W, H = 1920, 1080


def run(args: list[str]) -> None:
    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"ffmpeg failed: {' '.join(args[:12])}...\n{r.stderr[-2000:]}")


def duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    return float(out.stdout.strip())


def take_video(take: str) -> tuple[Path, float]:
    """The take's frames at a steady 30 fps, starting at the take's reference (mic start or first mark). Returns (mp4, offset):
    take-clock time t is at video time t - offset."""
    d = json.loads((RAW / take / "take.json").read_text())
    frames, ref = d["frames"], d.get("micStart", d["frames"][0]["t"])
    end = max(m["t"] for m in d["marks"])
    out = BUILD / "takes" / f"{take}.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    if not out.exists():
        lines = ["ffconcat version 1.0"]
        for i, f in enumerate(frames):
            nxt = frames[i + 1]["t"] if i + 1 < len(frames) else end  # Chrome sends a frame only on change: hold the last one
            lines += [f"file '{RAW / take / 'frames' / f['name']}'", f"duration {max(0.001, nxt - f['t']):.4f}"]
        lines.append(f"file '{RAW / take / 'frames' / frames[-1]['name']}'")
        lst = BUILD / "takes" / f"{take}.ffconcat"
        lst.write_text("\n".join(lines) + "\n")
        run(["-f", "concat", "-safe", "0", "-i", str(lst), "-vf", f"fps={FPS},scale={W}:{H}:flags=lanczos,format=yuv420p",
             "-c:v", "libx264", "-preset", "medium", "-crf", "14", str(out)])
    return out, frames[0]["t"] - ref


def segment(i: int, seg: dict) -> tuple[Path, float]:
    out = BUILD / "segs" / f"{i:02d}_{seg['id']}.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    caps = [(f"cap_{seg['id']}_{k}", c["at"], c["for"]) for k, c in enumerate(seg.get("captions", []))]
    labs = [(f"lab_{seg['id']}_{k}", l["at"], l["for"]) for k, l in enumerate(seg.get("labels", []))]
    overlays = caps + labs
    if "card" in seg:
        dur = seg["dur"]
        inputs = ["-loop", "1", "-t", f"{dur}", "-i", str(OV / f"card_{seg['card']}.png")]
        chain = f"[0:v]fps={FPS},format=yuv420p[base]"
    else:
        src, off = take_video(seg["take"])
        a, b = seg["from"] - off, seg["to"] - off
        hold = seg.get("hold", 0.0)
        dur = (b - a) + hold
        inputs = ["-ss", f"{max(0, a):.3f}", "-t", f"{b - a:.3f}", "-i", str(src)]
        chain = f"[0:v]setpts=PTS-STARTPTS,tpad=stop_mode=clone:stop_duration={hold:.3f},fps={FPS}"
        if seg.get("blur_pdf_numbers"):
            # The PDF prints a full (fictional) routing and account number under "How to pay". Blur it in both scroll positions.
            chain += (",split=3[v0][c1][c2];[c1]crop=230:170:640:515,boxblur=14[b1];[c2]crop=220:110:645:380,boxblur=14[b2];"
                      "[v0][b1]overlay=640:515:enable='between(t,0,1.65)'[v1];[v1][b2]overlay=645:380:enable='gte(t,1.6)'")
        chain += "[base]"
    for name, _, _ in overlays:
        inputs += ["-i", str(OV / f"{name}.png")]
    last = "base"
    for k, (name, at, length) in enumerate(overlays, start=1):
        nxt = f"o{k}"
        chain += f";[{last}][{k}:v]overlay=0:0:enable='between(t,{at:.2f},{at + length:.2f})'[{nxt}]"
        last = nxt
    run([*inputs, "-filter_complex", chain, "-map", f"[{last}]", "-t", f"{dur:.3f}", "-r", str(FPS),
         "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p", "-an", str(out)])
    return out, duration(out)


def build(name: str, ids: list[str] | None = None) -> Path:
    tl = json.loads((HERE / "timeline.json").read_text())
    segs = [s for s in tl["segments"] if ((s["id"] in ids) if ids is not None else not s.get("only"))]
    parts, t, audio = [], 0.0, []
    for i, seg in enumerate(segs):
        path, dur = segment(i, seg)
        parts.append(path)
        if "mic" in seg:
            m = seg["mic"]
            audio.append({"file": RAW / seg["take"] / "mic.wav", "start": t, "trim": (seg["from"], seg["to"]), "gain": m["gain"], "duck": m.get("duck")})
        if "vo" in seg:
            audio.append({"file": HERE / "vo" / f"{seg['vo']['file']}.wav", "start": t + seg["vo"]["at"], "gain": 1.0})
        t += dur
    total = t

    lst = BUILD / f"{name}.concat"
    lst.write_text("".join(f"file '{p}'\n" for p in parts))
    video = BUILD / f"{name}.video.mp4"
    run(["-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(video)])

    # Audio: every clip placed on one timeline, then loudness-normalized for speech.
    inputs, chains, labels = [], [], []
    for k, a in enumerate(audio):
        inputs += ["-i", str(a["file"])]
        f = f"[{k}:a]aformat=sample_rates=48000:channel_layouts=mono"
        if "trim" in a:
            s, e = a["trim"]
            f += f",atrim={s:.3f}:{e:.3f},asetpts=PTS-STARTPTS,highpass=f=110,lowpass=f=7500,volume={a['gain']}"
            if a.get("duck"):
                ds, de, g = a["duck"]
                f += f",volume={g}:enable='between(t,{ds},{de})'"
            f += ",afade=t=in:d=0.08,areverse,afade=t=in:d=0.12,areverse"
        f += f",adelay={int(a['start'] * 1000)}:all=1[a{k}]"
        chains.append(f)
        labels.append(f"[a{k}]")
    mix = ";".join(chains) + f";{''.join(labels)}amix=inputs={len(labels)}:normalize=0:dropout_transition=0,apad=whole_dur={total:.3f}," \
                             f"loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000[aout]"
    wav = BUILD / f"{name}.audio.wav"
    run([*inputs, "-filter_complex", mix, "-map", "[aout]", "-t", f"{total:.3f}", "-ac", "2", str(wav)])

    final = HERE / f"{name}.mp4"
    run(["-i", str(video), "-i", str(wav), "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "slow", "-crf", "20",
         "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-c:a", "aac", "-b:a", "192k", "-shortest", str(final)])
    print(f"{final.name}: {duration(final):.1f} s, {final.stat().st_size / 1e6:.1f} MB")
    return final


if __name__ == "__main__":
    build("countersign-launch")
    build("countersign-30s", ["cold_call", "cold_blocked", "intro", "close_short", "end_short"])
