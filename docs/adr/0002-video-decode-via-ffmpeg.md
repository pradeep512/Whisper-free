# Video Media files are decoded via an explicit ffmpeg subprocess, audio stays on librosa

## Status

accepted

## Context & decision

Whisper-Free now accepts video Media files (see [[CONTEXT.md]] — "Media file"), transcribing their audio track. Existing audio files are decoded by `librosa.load()` (audioread → ffmpeg), which reads PCM frame-by-frame through a Python pipe. That path works for video containers too, but audioread is slow and fragile on long media — and video skews long (lectures, meetings, movies), where a one-hour file can take minutes just to decode.

We therefore decode **video** with a direct ffmpeg subprocess (`ffmpeg -i <file> -ar 16000 -ac 1 -f wav <temp>`), then load the temp WAV via the fast soundfile path and delete it. **Audio** formats keep their existing librosa path unchanged, so no audio regression risk. This deliberately leaves two decode paths in the codebase; the asymmetry is the cost of buying fast, robust video decode without touching the working audio path.

## Considered options

- **Reuse `librosa.load()` for video too** (one decode path, a one-line allowlist change). Rejected: audioread's decode speed and reliability on long video is the exact pain this feature would hit first.
- **Route all ffmpeg-requiring formats (incl. mp3/m4a) through the explicit subprocess** (one unified path). Deferred, not rejected: it's a larger refactor with regression risk on the working audio path; the new helper is written so audio formats *can* migrate later.

## Consequences

- Two decode paths coexist by design; a future reader should not "simplify" them into one without re-checking long-media decode performance.
- Video decode hard-requires an ffmpeg binary (bundled in the installed build; must be on PATH for source runs) — there is no soundfile fallback for containers.
- `.srt`/`.vtt` output against a video file yields subtitles as a natural side effect.
