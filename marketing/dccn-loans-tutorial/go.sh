set -e
N=4710; C=4; step=$(( (N+C-1)/C ))
for i in $(seq 0 $((C-1))); do FROM=$((i*step)) TO=$(((i+1)*step)) OUT=part$i.mp4 node render.js > log$i.txt 2>&1 & done
wait
printf "file 'part0.mp4'\nfile 'part1.mp4'\nfile 'part2.mp4'\nfile 'part3.mp4'\n" > parts.txt
ffmpeg -v error -y -f concat -safe 0 -i parts.txt -i audio.wav -c:v copy -c:a aac -b:a 192k -shortest -movflags +faststart dccn_tutorial.mp4
ffprobe -v error -show_entries format=duration,size:stream=codec_name,width,height,r_frame_rate dccn_tutorial.mp4
