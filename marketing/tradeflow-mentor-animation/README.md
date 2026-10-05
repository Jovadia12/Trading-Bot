# TradeFlow Mentor — product animation

`tradeflow_mentor.mp4` — 10 s, 1920×1080, 60 fps, H.264.

The original screenshot (`src.png`) is the base layer and is never altered; the browser chrome is cropped off
and the app is shown as a floating window. Cursor, typing, chat messages, stat glows, data links, light and
particles are overlays rendered in `anim.html` (deterministic `render(t)`), then captured frame-by-frame.

Re-render (needs Node, Playwright + Chromium, ffmpeg):

    cd marketing/tradeflow-mentor-animation
    node render.js                          # -> out.mp4
    STILLS=3.6,6.6,8.0 node render.js       # preview single frames

Edit the question (`Q`), the mentor reply (`REPLY`), timings or the camera keyframes (`CAM`) at the top of the script in `anim.html`.
Font: Inter (SIL OFL).
