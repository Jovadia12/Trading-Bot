# DCCN Loans — customer journey animation

`dccn_journey.mp4` — 20 s, 1920×1080, 60 fps, H.264.

Dashboard → Apply for Loan → wallet + amount → Continue → stepper to Submitted → "Application Submitted /
Your application is being reviewed." → approval email (LOAN APPROVED) → dashboard activity
(Loan Approved, Escrow Transfer Confirmed, Funds Sent) → end card.

`dash.png` / `apply.png` are the original screenshots (browser chrome cropped) and are never altered; everything
else is an overlay in `anim.html`. Steps 2–5 of the application are not shown as pages (no reference screens) —
the stepper advances instead. The inbox is a neutral, unbranded mail client.

Re-render: `node render.js` (-> out.mp4) or `STILLS=4.9,13.4 node render.js` for preview frames.
Tweak timings (`T`), camera (`CAM`), copy (HTML), loan amount ("50") inside `anim.html`.
