"""
Generate PDF guide: README.md → Beautiful HTML → PDF via Edge headless.
Usage: python generate_pdf.py
"""
import markdown
import re
import os
import subprocess
import base64

README_PATH = 'README.md'
OUTPUT_HTML = 'AlgoTik_TSE_Guide.html'
OUTPUT_PDF = 'AlgoTik_TSE_Guide.pdf'
VERSION = '1.0.0'

# ── Persian/Arabic character detection ──────────────────────────
PERSIAN_RE = re.compile(r'[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF]')
LATIN_RE = re.compile(r'[A-Za-z]')

def is_predominantly_persian(text):
    """Check if text is predominantly Persian, ignoring code snippets."""
    clean = re.sub(r'<code>.*?</code>', '', text, flags=re.DOTALL)  # strip code elements
    clean = re.sub(r'<[^>]+>', '', clean)   # strip HTML tags
    clean = re.sub(r'`[^`]*`', '', clean)   # strip inline code in markdown
    # Remove anything that looks like code (function calls, etc.)
    clean = re.sub(r'[A-Za-z_]\w*\([^)]*\)', '', clean)
    persian_count = len(PERSIAN_RE.findall(clean))
    latin_count = len(LATIN_RE.findall(clean))
    return persian_count > 0 and persian_count >= latin_count

def is_code_only(text):
    """Check if text is only a code element with no significant Persian text outside it."""
    without_code = re.sub(r'<code>.*?</code>', '', text, flags=re.DOTALL)
    without_tags = re.sub(r'<[^>]+>', '', without_code).strip()
    return len(without_tags) < 3  # basically only code

def add_rtl_attrs(html_body):
    """Add dir=rtl and text-align:right to elements with predominantly Persian text."""
    def _rtl_element(match):
        tag = match.group(1)
        attrs = match.group(2) or ''
        content = match.group(3)
        if 'dir=' in attrs:
            return match.group(0)
        # Skip if content is essentially just code (no Persian text outside code)
        if '<code>' in content and is_code_only(content):
            return match.group(0)
        if is_predominantly_persian(content):
            return '<{}{} dir="rtl" style="text-align:right">{}</{}>'.format(
                tag, attrs, content, tag)
        return match.group(0)

    # Block-level elements
    for tag in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'li', 'th', 'td']:
        html_body = re.sub(
            r'<(' + tag + r')((?:\s[^>]*)?)>(.*?)</' + tag + r'>',
            _rtl_element, html_body, flags=re.DOTALL)
    return html_body

# ── Read README ──────────────────────────────────────────────────
with open(README_PATH, 'r', encoding='utf-8') as f:
    md_text = f.read()

# ── Clean up markdown for PDF ───────────────────────────────────
md_text = re.sub(r'\[!\[.*?\]\(.*?\)\]\(.*?\)\n?', '', md_text)
md_text = re.sub(r'<div[^>]*>', '', md_text)
md_text = re.sub(r'</div>', '', md_text)
md_text = re.sub(r'<details>\s*', '', md_text)
md_text = re.sub(r'</details>\s*', '', md_text)
md_text = re.sub(r'<summary>(.*?)</summary>\s*', r'**\1**\n\n', md_text)
md_text = re.sub(r'<code>(.*?)</code>', r'`\1`', md_text)

# ── Convert Markdown to HTML ────────────────────────────────────
html_body = markdown.markdown(
    md_text,
    extensions=['tables', 'fenced_code', 'toc', 'attr_list'],
    output_format='html5',
)

# ── Add RTL to Persian content ──────────────────────────────────
print("Adding RTL attributes to Persian content...")
html_body = add_rtl_attrs(html_body)

# ── Read Vazirmatn font and base64 encode for embedding ─────────
FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fonts')
font_regular_path = os.path.join(FONT_DIR, 'Vazirmatn-Regular.ttf')
font_bold_path = os.path.join(FONT_DIR, 'Vazirmatn-Bold.ttf')

with open(font_regular_path, 'rb') as f:
    font_regular_b64 = base64.b64encode(f.read()).decode('ascii')
with open(font_bold_path, 'rb') as f:
    font_bold_b64 = base64.b64encode(f.read()).decode('ascii')

# ── Full HTML document ──────────────────────────────────────────
html_doc = """<!DOCTYPE html>
<html lang="fa" dir="ltr">
<head>
<meta charset="utf-8">
<title>AlgoTik TSE — User Guide</title>
<style>
@font-face {
    font-family: 'Vazirmatn';
    src: url(data:font/truetype;base64,""" + font_regular_b64 + """) format('truetype');
    font-weight: normal;
    font-style: normal;
}
@font-face {
    font-family: 'Vazirmatn';
    src: url(data:font/truetype;base64,""" + font_bold_b64 + """) format('truetype');
    font-weight: bold;
    font-style: normal;
}

@page {
    size: A4;
}

* { box-sizing: border-box; }

body {
    font-family: 'Vazirmatn', Tahoma, 'Segoe UI', sans-serif;
    font-size: 11px;
    line-height: 1.75;
    color: #1a1a1a;
    max-width: 100%;
    padding: 0;
    margin: 0;
}

/* ── Cover Page ── */
.cover {
    text-align: center;
    padding-top: 100px;
    page-break-after: always;
}
.cover h1 {
    font-size: 48px;
    font-weight: 800;
    color: #0d6efd;
    margin-bottom: 10px;
    border: none;
    letter-spacing: 3px;
}
.cover .subtitle-en {
    font-size: 16px;
    color: #444;
    margin: 8px 0;
    font-weight: 600;
}
.cover .subtitle-fa {
    font-size: 15px;
    color: #555;
    margin: 8px 0;
    font-weight: 600;
    direction: rtl;
}
.cover .python-badge {
    display: inline-block;
    background: linear-gradient(135deg, #306998, #FFD43B);
    color: white;
    font-size: 13px;
    font-weight: 700;
    padding: 6px 24px;
    border-radius: 20px;
    margin: 18px 0;
    letter-spacing: 1px;
}
.cover hr {
    width: 50%;
    margin: 25px auto;
    border: none;
    border-top: 3px solid #0d6efd;
}
.cover .tags {
    font-size: 13px;
    color: #777;
    margin: 8px 0;
}
.cover .tags-fa {
    font-size: 13px;
    color: #777;
    direction: rtl;
    margin: 8px 0;
}
.cover .version {
    font-size: 12px;
    color: #999;
    margin-top: 40px;
}
.cover .website {
    font-size: 13px;
    color: #0d6efd;
    font-weight: 600;
}
.cover .author {
    font-size: 11px;
    color: #aaa;
    margin-top: 60px;
}

/* ── Headings ── */
h1 {
    font-size: 32px;
    font-weight: 800;
    color: #0d6efd;
    text-align: center;
    margin-top: 50px;
    margin-bottom: 8px;
    padding-bottom: 12px;
    border-bottom: 3px solid #0d6efd;
    letter-spacing: 1px;
    page-break-after: avoid;
}

h2 {
    font-size: 20px;
    font-weight: 700;
    color: #0d6efd;
    margin-top: 35px;
    margin-bottom: 12px;
    padding-bottom: 6px;
    border-bottom: 2px solid #e0e0e0;
    page-break-after: avoid;
}

h3 {
    font-size: 15px;
    font-weight: 700;
    color: #1565c0;
    margin-top: 25px;
    margin-bottom: 8px;
    page-break-after: avoid;
}

h4 {
    font-size: 13px;
    font-weight: 600;
    color: #333;
    margin-top: 18px;
    margin-bottom: 6px;
    page-break-after: avoid;
}

h5 {
    font-size: 12px;
    font-weight: 600;
    color: #555;
    margin-top: 12px;
}

/* ── Text ── */
p {
    margin: 6px 0;
}

strong {
    font-weight: 700;
    color: #222;
}

a {
    color: #0d6efd;
    text-decoration: none;
}

/* ── Code ── */
pre {
    background: #f6f8fa;
    border: 1px solid #d0d7de;
    border-radius: 8px;
    padding: 12px 16px;
    font-family: 'Cascadia Code', 'Consolas', 'Fira Code', monospace;
    font-size: 10px;
    line-height: 1.5;
    overflow-x: auto;
    white-space: pre-wrap;
    word-wrap: break-word;
    page-break-inside: avoid;
    margin: 8px 0 12px 0;
    direction: ltr;
    text-align: left;
}

code {
    background: #eff1f3;
    border-radius: 4px;
    padding: 1px 5px;
    font-family: 'Cascadia Code', 'Consolas', monospace;
    font-size: 10px;
    color: #c7254e;
    direction: ltr;
}

pre code {
    background: none;
    border: none;
    padding: 0;
    color: #24292f;
}

/* ── Tables ── */
table {
    width: 100%;
    border-collapse: collapse;
    margin: 10px 0 15px 0;
    font-size: 10px;
    page-break-inside: avoid;
}

thead { background: #0d6efd; }

th {
    padding: 8px 10px;
    font-weight: 600;
    font-size: 10px;
    color: white;
    border: 1px solid #0d6efd;
}

td {
    padding: 6px 10px;
    border: 1px solid #e8e8e8;
    font-size: 10px;
}

tr:nth-child(even) { background: #f8f9fa; }

/* ── Lists ── */
ul, ol {
    margin: 6px 0;
    padding-left: 22px;
}
li { margin: 3px 0; }

/* RTL list items */
li[dir="rtl"] {
    padding-left: 0;
    padding-right: 6px;
}

/* ── Blockquotes ── */
blockquote {
    border-left: 4px solid #ffc107;
    background: #fff8e1;
    padding: 10px 16px;
    margin: 10px 0;
    border-radius: 0 6px 6px 0;
}

/* ── Horizontal rules ── */
hr {
    border: none;
    border-top: 1px solid #ddd;
    margin: 25px 0;
}

/* ── Output label ── */
p > strong:only-child {
    display: block;
    background: #e8f0fe;
    color: #1a73e8;
    padding: 4px 10px;
    border-radius: 4px;
    font-size: 10px;
    margin: 8px 0 2px 0;
}
</style>
</head>
<body>

<!-- Cover Page -->
<div class="cover">
    <h1 style="border:none; text-align:center;">AlgoTik TSE</h1>
    <p class="subtitle-en">Tehran Stock Exchange Data Library</p>
    <p class="subtitle-fa">کتابخانه جامع دریافت اطلاعات بازار بورس تهران</p>
    <p class="python-badge">&#x1F40D; Python Package</p>
    <hr>
    <p class="tags">Stocks &bull; Options &bull; ETFs &bull; Bonds &bull; Funds &bull; Currency</p>
    <p class="tags-fa">سهام &bull; اختیار معامله &bull; صندوق ETF &bull; اوراق بدهی &bull; صندوق‌ها &bull; ارز و سکه</p>
    <p class="version">Version """ + VERSION + """ &mdash; Python 3.8+</p>
    <p class="website">algotik.com</p>
    <p class="author">
        Author: Mohsen Alipour &mdash; alipour@algotik.ir<br>
        Telegram: @algotik
    </p>
</div>

<!-- Main Content -->
""" + html_body + """

</body>
</html>
"""

# ── Save HTML ───────────────────────────────────────────────────
print("Saving HTML...")
with open(OUTPUT_HTML, 'w', encoding='utf-8') as f:
    f.write(html_doc)
print("HTML saved: %s (%.0f KB)" % (OUTPUT_HTML, os.path.getsize(OUTPUT_HTML)/1024))

# ── Convert to PDF via Playwright (full control, NO browser header/footer) ──
from playwright.sync_api import sync_playwright

print("Generating PDF via Playwright...")
html_abs = os.path.abspath(OUTPUT_HTML)
pdf_abs = os.path.abspath(OUTPUT_PDF)
file_url = 'file:///' + html_abs.replace('\\', '/')

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.goto(file_url, wait_until='networkidle')
    page.pdf(
        path=pdf_abs,
        format='A4',
        display_header_footer=False,
        print_background=True,
        margin={
            'top': '2.5cm',
            'bottom': '2cm',
            'left': '2cm',
            'right': '2cm',
        },
    )
    browser.close()

if os.path.exists(OUTPUT_PDF) and os.path.getsize(OUTPUT_PDF) > 0:
    size_kb = os.path.getsize(OUTPUT_PDF) / 1024
    print("PDF generated: %s (%.0f KB)" % (OUTPUT_PDF, size_kb))
else:
    print("ERROR: PDF not generated.")
    exit(1)

# Clean up HTML
os.remove(OUTPUT_HTML)
print("HTML cleaned up.")

# ── Add page numbers via post-processing ────────────────────────
print("Adding header & page numbers...")
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.colors import HexColor
from io import BytesIO

reader = PdfReader(OUTPUT_PDF)
total_pages = len(reader.pages)
writer = PdfWriter()

LEFT_MARGIN = 56.7    # 2cm in points
RIGHT_EDGE = 538.6    # A4 width (595.27) - 2cm
HEADER_Y = 808        # ~1.2cm from top edge
FOOTER_Y = 25         # ~0.9cm from bottom edge
LINE_Y = 801          # underline below header text

for i, page in enumerate(reader.pages):
    page_num = i + 1
    packet = BytesIO()
    c = rl_canvas.Canvas(packet, pagesize=A4)
    w, h = A4  # 595.27, 841.89

    # ── Header: "AlgoTik TSE" left, "v1.0.0" right ──
    c.setFont("Helvetica", 7)
    c.setFillColor(HexColor('#999999'))
    c.drawString(LEFT_MARGIN, HEADER_Y, "AlgoTik TSE")
    c.drawRightString(RIGHT_EDGE, HEADER_Y, "v" + VERSION)
    # thin line under header
    c.setStrokeColor(HexColor('#e0e0e0'))
    c.setLineWidth(0.5)
    c.line(LEFT_MARGIN, LINE_Y, RIGHT_EDGE, LINE_Y)

    # ── Footer: page number centered ──
    c.setFillColor(HexColor('#999999'))
    c.setFont("Helvetica", 7)
    footer_text = "%d / %d" % (page_num, total_pages)
    c.drawCentredString(w / 2, FOOTER_Y, footer_text)
    # thin line above footer
    c.setStrokeColor(HexColor('#e0e0e0'))
    c.line(LEFT_MARGIN, FOOTER_Y + 12, RIGHT_EDGE, FOOTER_Y + 12)

    c.save()
    packet.seek(0)

    overlay_reader = PdfReader(packet)
    page.merge_page(overlay_reader.pages[0])
    writer.add_page(page)

with open(OUTPUT_PDF, 'wb') as f:
    writer.write(f)

final_kb = os.path.getsize(OUTPUT_PDF) / 1024
print("Done! Final PDF: %s (%.0f KB, %d pages)" % (OUTPUT_PDF, final_kb, total_pages))
