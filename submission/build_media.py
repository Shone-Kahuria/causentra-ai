"""Build submission cover, pitch PDF, and captioned demo video."""
from pathlib import Path
import subprocess

from PIL import Image, ImageDraw, ImageFont
from reportlab.pdfgen import canvas
import imageio_ffmpeg

OUT = Path(__file__).resolve().parent / "media"
OUT.mkdir(exist_ok=True)
W, H = 1600, 900
BG, PANEL, CYAN, GOLD, WHITE, MUTED = "#0b1220", "#14263b", "#00c8d7", "#d7b56d", "#f4f7fb", "#a9bacb"
FONT = Path("C:/Windows/Fonts/segoeui.ttf")
BOLD = Path("C:/Windows/Fonts/segoeuib.ttf")


def font(size, bold=False):
    return ImageFont.truetype(str(BOLD if bold else FONT), size)


def base(kicker, title, subtitle):
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, W, 14), fill=CYAN)
    d.text((92, 64), "CAUSENTRA AI", font=font(32, True), fill=CYAN)
    d.text((92, 159), kicker.upper(), font=font(25, True), fill=GOLD)
    d.text((92, 211), title, font=font(67, True), fill=WHITE)
    d.text((94, 315), subtitle, font=font(29), fill=MUTED)
    d.text((92, 845), "AMD Developer Hackathon ACT III  |  Reinvent Commerce  |  Synthetic prototype", font=font(21), fill=MUTED)
    return im, d


def panel(d, x, y, w, h, heading, lines, accent=CYAN):
    d.rounded_rectangle((x, y, x+w, y+h), radius=24, fill=PANEL, outline="#294158", width=2)
    d.rectangle((x+25, y+34, x+33, y+82), fill=accent)
    d.text((x+52, y+30), heading, font=font(33, True), fill=WHITE)
    for idx, line in enumerate(lines):
        d.text((x+34, y+102+idx*47), line, font=font(25), fill=MUTED)


slides = []
im, d = base("Predict. Reason. Prevent.", "See the disruption early", "Evidence-linked supply intelligence with human-controlled action")
panel(d, 92, 432, 440, 302, "Detect", ["Supplier delay received", "Incident linked to orders"])
panel(d, 580, 432, 440, 302, "Compare", ["Three scenarios scored", "Assumptions adjustable"])
panel(d, 1068, 432, 440, 302, "Control", ["Manager approval gate", "Sandbox execution only"])
slides.append(im)

im, d = base("The problem", "Disconnected records", "A retailer needs one path from supplier risk to customer impact.")
for x, label in [(110, "Supplier"), (475, "Purchase order"), (840, "Inventory"), (1205, "Customer order")]:
    d.rounded_rectangle((x, 465, x+285, 605), radius=21, fill=PANEL, outline=CYAN, width=3)
    d.text((x+26, 508), label, font=font(30, True), fill=WHITE)
for x in (402, 767, 1132):
    d.text((x, 498), ">", font=font(56, True), fill=GOLD)
d.text((110, 677), "The incident retains source record IDs for inspection and audit.", font=font(28), fill=MUTED)
slides.append(im)

im, d = base("Working scenario", "8 units at risk", "Seven-day moving average: 8 units per day over a three-day horizon.")
panel(d, 92, 445, 435, 280, "24 units", ["Forecast demand", "Observed range: 21-27"])
panel(d, 580, 445, 435, 280, "16 units", ["Available inventory", "Receipt delayed to day 5"])
panel(d, 1068, 445, 435, 280, "8 units", ["Projected shortfall", "Scenario estimate only"], GOLD)
slides.append(im)

im, d = base("Decision lab", "Compare interventions", "Scores include projected exposure, added cost, and delayed-order penalty.")
panel(d, 92, 425, 440, 325, "Wait", ["8-unit shortfall", "$500 order exposure", "No added cost"])
panel(d, 580, 425, 440, 325, "Prioritize", ["8-unit shortfall", "$300 order exposure", "No added cost"])
panel(d, 1068, 425, 440, 325, "Expedite", ["8 units supplied", "$60 added cost", "No delayed orders"], GOLD)
slides.append(im)

im, d = base("Control plane", "Approval before action", "Analysts propose. A separate manager approves. Execution is simulated.")
panel(d, 92, 435, 680, 310, "Analyst", ["Inspect evidence and scenarios", "Create a pending proposal", "Cannot approve own action"])
panel(d, 830, 435, 680, 310, "Manager", ["Approve or reject proposal", "Execute in sandbox", "Review receipt and audit log"], GOLD)
slides.append(im)

im, d = base("Evidence and limits", "Working prototype", "Dockerized FastAPI app, public source, and a repeatable synthetic demo.")
panel(d, 92, 432, 680, 310, "Verified", ["16 automated tests passing", "Container and HTTP flow tested", "Seven-case rules baseline"])
panel(d, 830, 432, 680, 310, "Pending access", ["AMD adapter implemented", "Token Factory key unavailable", "Live model trace not claimed"], GOLD)
slides.append(im)

for index, image in enumerate(slides, 1):
    image.save(OUT / f"slide-{index:02}.png", optimize=True)
slides[0].save(OUT / "cover.png", optimize=True)

pdf = canvas.Canvas(str(OUT / "pitch.pdf"), pagesize=(960, 540))
for index in range(1, len(slides)+1):
    pdf.drawImage(str(OUT / f"slide-{index:02}.png"), 0, 0, width=960, height=540)
    pdf.showPage()
pdf.save()

concat = OUT / "video-list.txt"
concat.write_text("".join(f"file 'slide-{i:02}.png'\nduration 7\n" for i in range(1, len(slides)+1))
                  + f"file 'slide-{len(slides):02}.png'\n", encoding="utf-8")
subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-f", "concat", "-safe", "0", "-i", str(concat),
                "-vf", "scale=1280:720,format=yuv420p", "-r", "24", "-c:v", "libx264", "-preset", "veryfast",
                "-crf", "23", "-movflags", "+faststart", str(OUT / "demo.mp4")], check=True,
               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
concat.unlink()
print("Built cover.png, pitch.pdf, demo.mp4")
