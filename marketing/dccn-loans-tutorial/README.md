# DCCN Loans — onboarding / tutorial video

`dccn_tutorial.mp4` — 78.5 s, 1920×1080, 60 fps, H.264 + AAC (voiceover, music, UI sounds; loudness -16 LUFS).

Flow (the five screenshots, in the order supplied): Dashboard → Apply for a Loan (wallet, amount, stepper,
"Application Submitted") → My Loans → Loan History → Payment Preferences → approval email → dashboard
("Loan Approved", track to funding) → end card. Burned-in captions follow the voiceover.

Screenshots are never altered; all motion is overlays in `anim.html`.

Pipeline
1. `voiceover/vo.py` — Kokoro TTS (voice `af_heart`) writes `v1..v9.wav` + `durs.json`.
   Needs `pip install kokoro-onnx soundfile numpy` and the model files from
   github.com/thewh1teagle/kokoro-onnx releases (`kokoro-v1.0.onnx`, `voices-v1.0.bin`).
2. `build.py` — places the lines on the timeline, writes `timeline.js` (camera, cursor, captions, events)
   and `audio.wav` (voice + generated music with ducking + UI sound effects).
3. `go.sh` — renders frames with Playwright in 4 parallel chunks and muxes the audio.
   Then loudness-normalise: `ffmpeg -i dccn_tutorial.mp4 -c:v copy -af loudnorm=I=-16:TP=-1.5 ...`
