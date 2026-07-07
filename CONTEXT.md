# Whisper-Free

A local, offline desktop app that turns speech into text — from a live push-to-talk recording or from files the user already has — using a local Whisper model. Nothing leaves the machine.

## Language

**Media file**:
A user-supplied audio *or* video file offered for transcription. The canonical umbrella term for anything the user feeds in from disk; a video is treated as a carrier of an audio track.
_Avoid_: "audio file" (misleading once video is accepted), "clip", "recording" (reserve "recording" for live capture, below).

**Recording**:
Audio captured live by the app from the microphone via push-to-talk, as opposed to a file loaded from disk.
_Avoid_: using "recording" for an imported Media file.

**Transcription**:
The text produced from a Media file or Recording, together with its detected language and time-coded segments.

**Batch transcription**:
Transcribing several Media files in sequence as one user-initiated run, with per-file status, retry, and an overall progress view.
_Avoid_: "queue" (that's the internal mechanism), "bulk".
