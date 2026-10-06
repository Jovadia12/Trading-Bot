import soundfile as sf, json, sys
from kokoro_onnx import Kokoro
k=Kokoro("kokoro-v1.0.onnx","voices-v1.0.bin")
VOICE=sys.argv[1] if len(sys.argv)>1 else "af_heart"
LINES=[
 ("v1","Welcome to DCCN Loans. Getting started is simple. Your dashboard brings everything together: your collateral, what's available to borrow, your active loans, and your recent activity."),
 ("v2","When you're ready, select Apply for Loan. Choose a verified wallet as collateral, and enter the amount you'd like to borrow, up to seventy percent of your verified wallet balance."),
 ("v3","Then continue through each step: your loan offer, repayment plan, review, and agreement."),
 ("v4","In My Loans, you can see every loan's collateral, amount, amount owed, due date, and status, and download your agreement at any time."),
 ("v5","Loan History keeps a complete record of what you borrowed, what you received, what you owe, your term, and the transaction I D."),
 ("v6","And in Payment Preferences, you choose how you'd like to receive your funds: Zelle, Venmo, wire transfer, or PayPal."),
 ("v7","Once your application has been reviewed and approved, you'll receive a confirmation by email."),
 ("v8","From there, follow the next steps in your dashboard, and track your loan through funding."),
 ("v9","DCCN Loans. A simpler way to navigate your financing journey."),
]
out={}
for key,txt in LINES:
    a,sr=k.create(txt,voice=VOICE,speed=1.0,lang="en-us")
    sf.write(f"{key}.wav",a,sr); out[key]=len(a)/sr; print(key,round(len(a)/sr,2))
json.dump(out,open("durs.json","w"))
print("total",round(sum(out.values()),1))
