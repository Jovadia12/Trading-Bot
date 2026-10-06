set -e
N=4710; C=4; step=$(( (N+C-1)/C ))
for i in $(seq 0 $((C-1))); do FROM=$((i*step)) TO=$(((i+1)*step)) OUT=part$i.mp4 node render.js > log$i.txt 2>&1 & done
wait
printf "file 'part0.mp4'\nfile 'part1.mp4'\nfile 'part2.mp4'\nfile 'part3.mp4'\n" > parts.txt
ffmpeg -v error -y -f concat -safe 0 -i parts.txt -i audio.wav -c:v copy -c:a aac -b:a 192k -shortest -movflags +faststart raw.mp4
ffprobe -v error -show_entries format=duration,size:stream=codec_name,width,height,r_frame_rate raw.mp4
ffmpeg -v error -y -i raw.mp4 -c:v copy -af loudnorm=I=-16:TP=-1.5:LRA=11 -ar 48000 -c:a aac -b:a 192k -movflags +faststart tradeflow_promo.mp4
ffmpeg -v error -y -i tradeflow_promo.mp4 -c:v libx264 -preset slow -crf 22 -tune animation -pix_fmt yuv420p -c:a copy -movflags +faststart preview.mp4
ls -la tradeflow_promo.mp4 preview.mp4
