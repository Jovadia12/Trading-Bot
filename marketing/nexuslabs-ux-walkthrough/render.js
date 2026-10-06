const {chromium}=require('playwright');
const {spawn}=require('child_process');
const FPS=+process.env.FPS||60;
(async()=>{
  const b=await chromium.launch();const p=await b.newPage({viewport:{width:1920,height:1080},deviceScaleFactor:1});
  p.on('pageerror',e=>console.error('PAGEERR',e));
  await p.goto('file://'+process.cwd()+'/anim.html');await p.evaluate(()=>document.fonts.ready);await p.waitForTimeout(300);
  const stills=process.env.STILLS;
  if(stills){for(const t of stills.split(',')){await p.evaluate(async t=>{await render(t)},+t);await p.screenshot({path:`still_${t}.png`});}await b.close();return;}
  const dur=await p.evaluate(()=>DUR);const N=Math.round(dur*FPS);
  const ff=spawn('ffmpeg',['-y','-v','error','-f','image2pipe','-framerate',String(FPS),'-c:v','png','-i','-','-c:v','libx264','-preset','slow','-crf','14','-pix_fmt','yuv420p','-tune','animation','-movflags','+faststart',process.env.OUT||'out.mp4'],{stdio:['pipe','inherit','inherit']});
  const A=+(process.env.FROM||0),B=+(process.env.TO||N);for(let i=A;i<Math.min(B,N);i++){await p.evaluate(async t=>{await render(t)},i/FPS);const buf=await p.screenshot({type:'png'});if(!ff.stdin.write(buf))await new Promise(r=>ff.stdin.once('drain',r));if(i%60==0)console.log('frame',i,'/',N);}
  ff.stdin.end();await new Promise(r=>ff.on('close',r));await b.close();console.log('done');
})();
