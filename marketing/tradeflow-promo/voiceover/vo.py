import soundfile as sf, json, sys
from kokoro_onnx import Kokoro
k=Kokoro("kokoro-v1.0.onnx","voices-v1.0.bin")
VOICE=sys.argv[1] if len(sys.argv)>1 else "af_heart"
LINES=[
 ("v1","Meet TradeFlow: your all-in-one trading performance platform, built to help you trade smarter, stay disciplined, and understand your performance."),
 ("v2","Start your day with a complete view of your trading. Track your results, review recent trades, follow your daily checklist, and stay focused on your goals."),
 ("v3","Before you trade, know what's happening in the market. The Economic Calendar helps you spot high-impact events and potential market-moving releases before they happen."),
 ("v4","Then see your performance over time with the P and L Calendar. Understand your daily and weekly results at a glance, and identify patterns in your trading."),
 ("v5","Want to test an idea before putting real money at risk? Use Paper Trading to practice your strategy, analyze the market, and test your decisions in a simulated environment."),
 ("v6","And when you're working toward a payout, TradeFlow keeps it organized in one place: your valid profit days, payout split, account balance, and payout history."),
 ("v7","From market preparation to performance tracking, strategy testing, and payouts, TradeFlow brings your entire trading workflow together."),
 ("v8","TradeFlow. Know your data. Track your progress. Trade with purpose."),
]
out={}
for key,txt in LINES:
    a,sr=k.create(txt,voice=VOICE,speed=1.0,lang="en-us")
    sf.write(f"tf/{key}.wav",a,sr); out[key]=len(a)/sr; print(key,round(len(a)/sr,2))
json.dump(out,open("tf/durs.json","w"))
print("total",round(sum(out.values()),1))
