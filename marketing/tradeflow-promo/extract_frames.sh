# Extract the five source clips from the screen recording (60 fps JPEG frames into fr/).
# Usage: bash extract_frames.sh path/to/Screen_Recording.mov
R="$1"; mkdir -p fr
for seg in "dash 0.0 1.7" "econ 10.0 2.5" "pnl 22.6 5.1" "paper 32.5 2.7" "pay 39.5 4.9" "pay2 47.0 0.7"; do
  set -- $seg; ffmpeg -v error -y -ss $2 -i "$R" -t $3 -vf fps=60 -q:v 2 fr/${1}_%04d.jpg
done
