import soundfile as sf, json, sys
from kokoro_onnx import Kokoro
k=Kokoro("kokoro-v1.0.onnx","voices-v1.0.bin")
LINES=[
 ("v1","This walkthrough demonstrates the current NexusLabs Research website structure. We'll begin with the homepage, navigate through the available catalog categories, review the product catalog interface, access the COA Library, and finish by reviewing the affiliate-program section."),
 ("v2","The homepage has an announcement banner, then a header with the logo, a search field, four category links, an Affiliates link, and account and cart icons. Below it, the hero section contains Shop Now and Learn More buttons."),
 ("v3","Selecting Shop Now opens the shop page, titled The Archive. It includes a search field, category filter buttons, a maximum price slider, a sort menu, and a product count."),
 ("v4","Scrolling reveals the product grid. Each card shows an image, name, price, category label, and a View Options button, while the header stays fixed at the top."),
 ("v5","The COA Library sits further down the homepage, with a search field for compounds or batch IDs, and a grid of expandable entries listing each compound and its category."),
 ("v6","The affiliate section is in the account area, under the Affiliate tab. It has five sub-tabs, a row of summary metrics, three status cards, and a panel with the affiliate code and referral link."),
 ("v7","This concludes the walkthrough of the current NexusLabs Research website structure."),
]
out={}
for key,txt in LINES:
    a,sr=k.create(txt,voice="af_heart",speed=1.06,lang="en-us")
    sf.write(f"nx/{key}.wav",a,sr); out[key]=len(a)/sr; print(key,round(len(a)/sr,2))
json.dump(out,open("nx/durs.json","w")); print("total",round(sum(out.values()),1))
