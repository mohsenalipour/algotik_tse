"""Build the bilingual AlgoTik TSE PDF guide from README.md.

The default output is an approval preview. Pass ``--output`` after approval
to replace the repository's canonical ``AlgoTik_TSE_Guide.pdf``.
"""

import argparse
import base64
import html
from io import BytesIO
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unicodedata

import markdown
from markdown.extensions.toc import TocExtension
from pypdf import PdfReader, PdfWriter
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas as reportlab_canvas


ROOT = Path(__file__).resolve().parent
README_PATH = ROOT / "README.md"
FONT_DIR = ROOT / "fonts"
LOGO_PATH = ROOT / "docs" / "assets" / "algotik_logo_stacked_1024.png"
TMP_DIR = ROOT / "tmp" / "pdfs"
DEFAULT_OUTPUT = ROOT / "output" / "pdf" / "AlgoTik_TSE_Guide_v1.2.3_preview.pdf"
VERSION = "1.2.3"
RELEASE_DATE = "1 September 2026"


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--keep-html", action="store_true")
    return parser.parse_args()


def data_url(path):
    payload = base64.b64encode(path.read_bytes()).decode("ascii")
    return "data:font/truetype;base64," + payload


def image_data_url(path):
    payload = base64.b64encode(path.read_bytes()).decode("ascii")
    return "data:image/png;base64," + payload


def unicode_slugify(value, separator):
    """Create stable PDF anchors matching the README's Persian links."""
    value = html.unescape(re.sub(r"<[^>]+>", "", value))
    value = unicodedata.normalize("NFKC", value).strip().lower()
    value = value.replace("/", "").replace("\u200c", "")
    value = re.sub(r"[^\w\u0600-\u06ff،؛-]+", separator, value)
    value = re.sub(re.escape(separator) + r"+", separator, value)
    return value.strip(separator)


def clean_readme(text):
    """Remove web-only chrome while retaining all user documentation."""
    text = re.sub(r"\A\ufeff?# AlgoTik TSE\s*", "", text, count=1)
    text = re.sub(r"^\[!\[[^\n]+\n?", "", text, flags=re.MULTILINE)
    text = text.replace(
        '<div dir="rtl" align="right">',
        '<div class="rtl-content" dir="rtl" markdown="1">',
    )
    text = re.sub(r"<details>\s*", "", text)
    text = re.sub(r"</details>\s*", "", text)
    text = re.sub(r"<summary>(.*?)</summary>\s*", r"### \1\n\n", text)
    return text.strip()


def render_markdown(text):
    return markdown.markdown(
        text,
        extensions=[
            "tables",
            "fenced_code",
            TocExtension(slugify=unicode_slugify, permalink=False),
            "attr_list",
            "md_in_html",
            "sane_lists",
        ],
        output_format="html5",
    )


def build_html(body):
    regular_font = data_url(FONT_DIR / "Vazirmatn-Regular.ttf")
    bold_font = data_url(FONT_DIR / "Vazirmatn-Bold.ttf")
    logo = image_data_url(LOGO_PATH)
    return """<!doctype html>
<html lang="fa">
<head>
<meta charset="utf-8">
<meta name="author" content="Mohsen Alipour">
<meta name="description" content="AlgoTik TSE bilingual user guide">
<title>AlgoTik TSE {version} — User Guide</title>
<style>
@font-face {{ font-family: Vazirmatn; src: url("{regular}"); font-weight: 400; }}
@font-face {{ font-family: Vazirmatn; src: url("{bold}"); font-weight: 700 900; }}
@page {{ size: A4; margin: 22mm 18mm 19mm; }}
* {{ box-sizing: border-box; }}
html {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
body {{
  margin: 0; color: #20252b; background: #fff;
  font-family: Vazirmatn, Tahoma, "Segoe UI", sans-serif;
  font-size: 10.1pt; line-height: 1.82;
}}
a {{ color: #0d6efd; text-decoration: none; }}
p {{ margin: 0 0 7pt; orphans: 3; widows: 3; }}
strong {{ color: #17202a; font-weight: 700; }}
.rtl-content {{ direction: rtl; text-align: right; }}
.rtl-content p, .rtl-content li, .rtl-content td, .rtl-content th {{
  direction: rtl; text-align: right; unicode-bidi: plaintext;
}}
.rtl-content ul, .rtl-content ol {{ padding-right: 20pt; padding-left: 0; }}
.rtl-content code, .rtl-content pre {{ direction: ltr; text-align: left; unicode-bidi: embed; }}
bdi, code {{ direction: ltr; unicode-bidi: isolate; }}

.cover {{
  height: 250mm; page-break-after: always; text-align: center;
  display: flex; flex-direction: column; justify-content: center; align-items: center;
  position: relative;
}}
.cover::before {{
  content: ""; position: absolute; top: 8mm; left: 14mm; right: 14mm; height: 4px;
  border-radius: 4px; background: linear-gradient(90deg,#306998,#0d6efd,#ffd43b);
}}
.cover-logo {{
  display: block; width: 260px; height: 260px; object-fit: cover;
  border-radius: 22px; margin-bottom: 18px;
  box-shadow: 0 14px 34px #00102738;
}}
.cover .edition {{
  margin: 8px 0 22px; padding: 5px 18px; border-radius: 18px;
  background: #eaf2ff; color: #0d6efd; font-weight: 700; font-size: 10pt;
}}
.cover .subtitle-en {{ font-size: 15pt; font-weight: 700; color: #343a40; margin: 0 0 7px; }}
.cover .subtitle-fa {{ font-size: 14pt; font-weight: 700; color: #4d5966; direction: rtl; }}
.cover .rule {{ width: 58%; height: 3px; margin: 25px 0 20px; background: #0d6efd; border-radius: 2px; }}
.cover .tags {{ color: #6c757d; font-size: 10pt; margin: 4px 0; }}
.cover .tags-fa {{ color: #6c757d; font-size: 10pt; margin: 4px 0; direction: rtl; }}
.cover .meta {{ margin-top: 28px; color: #8a949e; font-size: 9.5pt; line-height: 1.9; }}
.cover .site {{ color: #0d6efd; font-weight: 700; }}

.reader-map {{ min-height: 245mm; page-break-after: always; direction: rtl; text-align: right; }}
.reader-map .eyebrow {{ color: #0d6efd; font-weight: 700; margin-top: 7mm; }}
.reader-map h1 {{ text-align: right; margin-top: 8px; }}
.reader-map .lead {{ font-size: 11.5pt; color: #44515d; }}
.path-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 20px; }}
.path-card {{ display: block; color: inherit; border: 1px solid #d9e6fa; border-radius: 12px; padding: 13px 15px; background: #f7faff; }}
.path-card:hover {{ border-color: #0d6efd; background: #eef5ff; }}
.path-card .num {{ color: #0d6efd; font-weight: 900; font-size: 15pt; }}
.path-card h3 {{ margin: 1px 0 4px; color: #153f73; }}
.path-card p {{ margin: 0; font-size: 9.2pt; }}
.legend {{ margin-top: 22px; border-right: 4px solid #ffd43b; background: #fff9df; padding: 11px 15px; }}

h1 {{
  color: #0d6efd; font-size: 25pt; line-height: 1.3; margin: 12pt 0 15pt;
  padding-bottom: 8pt; border-bottom: 3px solid #0d6efd; page-break-after: avoid;
}}
h2 {{
  color: #0d6efd; font-size: 18pt; line-height: 1.4; margin: 0 0 14pt;
  padding: 7pt 0 7pt; border-bottom: 2px solid #d8e6fa;
  break-before: auto; page-break-before: auto; page-break-after: avoid;
}}
h3 {{ color: #145eb3; font-size: 14pt; line-height: 1.5; margin: 18pt 0 7pt; page-break-after: avoid; }}
h4 {{ color: #263645; font-size: 11.5pt; margin: 14pt 0 5pt; page-break-after: avoid; }}
h5, h6 {{ color: #3f4c58; font-size: 10.5pt; margin: 11pt 0 4pt; page-break-after: avoid; }}
hr {{ border: 0; border-top: 1px solid #d9dee4; margin: 19pt 0; }}
ul, ol {{ margin-top: 4pt; margin-bottom: 9pt; }}
li {{ margin: 2.5pt 0; orphans: 2; widows: 2; }}

blockquote {{
  margin: 11pt 0; padding: 9pt 13pt; background: #fff8df;
  border-left: 4px solid #ffc107; border-radius: 6px;
}}
.rtl-content blockquote {{ border-left: 0; border-right: 4px solid #ffc107; }}
blockquote p:last-child {{ margin-bottom: 0; }}

code {{
  font-family: Consolas, "Cascadia Code", monospace; font-size: 8.7pt;
  color: #b42346; background: #f1f3f5; border-radius: 4px; padding: 1px 4px;
  white-space: normal; overflow-wrap: break-word; word-break: normal;
}}
pre {{
  direction: ltr; text-align: left; unicode-bidi: embed; white-space: pre-wrap;
  overflow-wrap: anywhere; word-break: break-word; tab-size: 4;
  break-inside: avoid; page-break-inside: avoid;
  margin: 8pt 0 13pt; padding: 11pt 13pt; border: 1px solid #ced8e3;
  border-radius: 9px; background: #f6f8fa; color: #1e2933;
  font: 8.2pt/1.55 Consolas, "Cascadia Code", monospace;
}}
pre code {{ color: inherit; background: transparent; padding: 0; font-size: inherit; white-space: inherit; }}

table {{
  width: 100%; border-collapse: collapse; margin: 9pt 0 15pt;
  font-size: 8.45pt; line-height: 1.55; break-inside: auto; page-break-inside: auto;
}}
thead {{ display: table-header-group; background: #0d6efd; color: #fff; }}
tfoot {{ display: table-footer-group; }}
tr {{ break-inside: avoid; page-break-inside: avoid; }}
th {{ color: #fff; font-weight: 700; padding: 7px 8px; border: 1px solid #0b5ed7; vertical-align: top; }}
td {{ padding: 6px 8px; border: 1px solid #dfe5eb; vertical-align: top; }}
tbody tr:nth-child(even) {{ background: #f7f9fb; }}
td:first-child {{ font-weight: 500; }}
table:has(thead th:nth-child(4)):not(:has(thead th:nth-child(5))) {{ table-layout: fixed; font-size: 8pt; }}
table:has(thead th:nth-child(4)):not(:has(thead th:nth-child(5))) th:nth-child(1),
table:has(thead th:nth-child(4)):not(:has(thead th:nth-child(5))) td:nth-child(1) {{ width: 18%; }}
table:has(thead th:nth-child(4)):not(:has(thead th:nth-child(5))) th:nth-child(2),
table:has(thead th:nth-child(4)):not(:has(thead th:nth-child(5))) td:nth-child(2) {{ width: 29%; }}
table:has(thead th:nth-child(4)):not(:has(thead th:nth-child(5))) th:nth-child(3),
table:has(thead th:nth-child(4)):not(:has(thead th:nth-child(5))) td:nth-child(3) {{ width: 27%; }}
table:has(thead th:nth-child(4)):not(:has(thead th:nth-child(5))) th:nth-child(4),
table:has(thead th:nth-child(4)):not(:has(thead th:nth-child(5))) td:nth-child(4) {{ width: 26%; }}
table:has(thead th:nth-child(4)):not(:has(thead th:nth-child(5))) code {{ overflow-wrap: anywhere; }}

img {{ max-width: 100%; }}
.manual > p:first-child {{ font-size: 11.5pt; color: #33404c; }}
.manual > p:nth-child(2) {{ margin-bottom: 18pt; }}
@media print {{ a {{ color: #0d6efd; }} }}
</style>
</head>
<body>
<section class="cover">
  <img class="cover-logo" src="{logo}" alt="AlgoTik logo">
  <div class="edition">نسخهٔ {version} · راهنمای کامل کاربر</div>
  <p class="subtitle-en">Tehran Stock Exchange Data &amp; Analytics Library</p>
  <p class="subtitle-fa">کتابخانهٔ داده و تحلیل بازار سرمایهٔ ایران</p>
  <div class="rule"></div>
  <p class="tags">Stocks · Live Market · Options · ETFs · Bonds · Currency</p>
  <p class="tags-fa">سهام · بازار زنده · اختیار معامله · صندوق · اوراق بدهی · ارز و سکه</p>
  <div class="meta">Python 3.8–3.14<br>{date}<br><span class="site">algotik.com</span><br>Mohsen Alipour · @algotik</div>
</section>

<section class="reader-map">
  <p class="eyebrow">راهنمای مطالعه</p>
  <h1>چطور از این دفترچه استفاده کنید؟</h1>
  <p class="lead">این راهنما دو لایه دارد: ابتدا مسیرهای سریع و توابعی که بیشتر کاربران هر روز نیاز دارند؛ سپس مرجع کامل ورودی‌ها، گزینه‌ها، خروجی‌ها و نکات رفتاری همهٔ APIهای عمومی پکیج.</p>
  <div class="path-grid">
    <a class="path-card" href="#شروع-سریع"><span class="num">۱</span><h3>شروع سریع</h3><p>نصب، import و اولین دریافت تاریخچهٔ قیمت در چند دقیقه.</p></a>
    <a class="path-card" href="#راهنمای-توابع-پرکاربرد"><span class="num">۲</span><h3>توابع پرکاربرد</h3><p>قیمت، حقیقی/حقوقی، بازار زنده، سفارش، ارز، صندوق، اخزا و اختیار.</p></a>
    <a class="path-card" href="#قراردادهای-مهم-داده"><span class="num">۳</span><h3>قراردادهای داده</h3><p>نوع خروجی، تاریخ، freshness، ردیف امروز، CSV و مرز منابع داده.</p></a>
    <a class="path-card" href="#مرجع-تفصیلی-همهٔ-توابع"><span class="num">۴</span><h3>مرجع تفصیلی</h3><p>signatureها، تمام ورودی‌ها، مقدارهای مجاز، پیش‌فرض‌ها و خروجی هر خانوادهٔ تابع.</p></a>
  </div>
  <div class="legend"><strong>نکتهٔ معاملاتی:</strong> پیش از استفاده در تصمیم‌گیری یا اجرای الگوریتم، زمان snapshot، ویژگی‌های <code>DataFrame.attrs</code>، وضعیت <code>partial</code> و freshness داده را بررسی کنید. این پکیج توصیهٔ سرمایه‌گذاری ارائه نمی‌کند.</div>
</section>

<main class="manual">
{body}
</main>
</body>
</html>
""".format(
        version=VERSION,
        date=RELEASE_DATE,
        logo=logo,
        regular=regular_font,
        bold=bold_font,
        body=body,
    )


def validate_internal_html_links(document):
    """Ensure every internal link has a concrete destination before printing."""
    element_ids = set(re.findall(r'\sid="([^"]+)"', document))
    targets = [html.unescape(value) for value in re.findall(r'href="#([^"]+)"', document)]
    missing = sorted(set(targets) - element_ids)
    if missing:
        raise RuntimeError("Internal PDF links have no destination: " + ", ".join(missing))
    if len(targets) < 15:
        raise RuntimeError("The guide contains too few internal navigation links.")
    return len(targets)


def find_edge():
    candidates = [
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Microsoft/Edge/Application/msedge.exe",
        Path(os.environ.get("PROGRAMFILES", "")) / "Microsoft/Edge/Application/msedge.exe",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    resolved = shutil.which("msedge")
    if resolved:
        return Path(resolved)
    raise RuntimeError("Microsoft Edge was not found; it is required for Persian PDF rendering.")


def html_to_pdf(html_path, pdf_path):
    edge = find_edge()
    profile_dir = Path(tempfile.mkdtemp(prefix="algotik-tse-pdf-edge-"))
    if pdf_path.exists():
        pdf_path.unlink()
    # Newer Edge builds in this environment crash unless GPU composition is fully
    # disabled in headless mode. Keep this flag set for reproducible rendering.
    command = [
        str(edge),
        "--headless=new",
        "--disable-gpu",
        "--disable-gpu-compositing",
        "--disable-gpu-rasterization",
        "--disable-software-rasterizer",
        "--disable-features=VizDisplayCompositor",
        "--disable-extensions",
        "--disable-background-mode",
        "--no-first-run",
        "--no-sandbox",
        "--no-pdf-header-footer",
        "--generate-pdf-document-outline",
        "--user-data-dir=" + str(profile_dir.resolve()),
        "--print-to-pdf=" + str(pdf_path.resolve()),
        html_path.resolve().as_uri(),
    ]
    subprocess.run(command, check=True, timeout=180)

    # Edge can return before the background PDF writer has flushed the file.
    deadline = time.monotonic() + 30
    previous_size = -1
    stable_checks = 0
    while time.monotonic() < deadline:
        if pdf_path.exists():
            current_size = pdf_path.stat().st_size
            if current_size > 0 and current_size == previous_size:
                stable_checks += 1
                if stable_checks >= 3:
                    shutil.rmtree(str(profile_dir), ignore_errors=True)
                    return
            else:
                stable_checks = 0
            previous_size = current_size
        time.sleep(0.5)
    shutil.rmtree(str(profile_dir), ignore_errors=True)
    raise RuntimeError("Edge did not finish writing the PDF within 30 seconds.")


def overlay_header_and_footer(pdf_path):
    reader = PdfReader(str(pdf_path))
    writer = PdfWriter()
    writer.clone_document_from_reader(reader)
    total_pages = len(writer.pages)
    left_margin = 51.0
    right_edge = 544.0

    for index, page in enumerate(writer.pages):
        packet = BytesIO()
        canvas = reportlab_canvas.Canvas(packet, pagesize=A4)
        width, _ = A4
        canvas.setFillColor(HexColor("#8b949e"))
        canvas.setStrokeColor(HexColor("#e1e6eb"))
        canvas.setLineWidth(0.45)
        canvas.line(left_margin, 808, right_edge, 808)
        canvas.line(left_margin, 35, right_edge, 35)
        canvas.setFont("Helvetica", 7)
        canvas.drawString(left_margin, 814, "AlgoTik TSE")
        canvas.drawRightString(right_edge, 814, "User Guide  |  v" + VERSION)
        canvas.drawCentredString(width / 2, 23, "%d / %d" % (index + 1, total_pages))
        canvas.save()
        packet.seek(0)
        overlay = PdfReader(packet).pages[0]
        page.merge_page(overlay)

    writer.add_metadata(
        {
            "/Title": "AlgoTik TSE %s - Complete User Guide" % VERSION,
            "/Author": "Mohsen Alipour",
            "/Subject": "Bilingual user guide for algotik-tse",
            "/Keywords": "TSETMC, Tehran Stock Exchange, Python, market data, options, bonds",
        }
    )
    staged = pdf_path.with_suffix(".numbered.pdf")
    with staged.open("wb") as stream:
        writer.write(stream)
    staged.replace(pdf_path)
    return total_pages


def validate_pdf(pdf_path):
    reader = PdfReader(str(pdf_path))
    if len(reader.pages) < 10:
        raise RuntimeError("The guide is unexpectedly short: %d pages" % len(reader.pages))
    if pdf_path.stat().st_size < 200_000:
        raise RuntimeError("The generated PDF is unexpectedly small.")
    sample_pages = list(reader.pages[:8]) + list(reader.pages[-5:])
    sample_text = "\n".join((page.extract_text() or "") for page in sample_pages)
    # Chromium embeds Persian glyphs correctly, but PDF text extractors can
    # reorder joined RTL characters. Keep automated content checks ASCII-only;
    # the rendered pages are inspected separately for RTL quality.
    for required in ("AlgoTik TSE", VERSION, "get_history", "License"):
        if required not in sample_text:
            raise RuntimeError("Generated PDF is missing expected text: " + required)
    for page in reader.pages:
        width = float(page.mediabox.width)
        height = float(page.mediabox.height)
        if not (590 <= width <= 600 and 837 <= height <= 846):
            raise RuntimeError("A non-A4 page was generated: %.1f x %.1f" % (width, height))


def main():
    args = parse_args()
    output_path = args.output
    if not output_path.is_absolute():
        output_path = ROOT / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    html_path = TMP_DIR / ("AlgoTik_TSE_Guide_v%s.html" % VERSION)

    markdown_text = clean_readme(README_PATH.read_text(encoding="utf-8"))
    html_body = render_markdown(markdown_text)
    html_document = build_html(html_body)
    internal_links = validate_internal_html_links(html_document)
    html_path.write_text(html_document, encoding="utf-8")
    print("HTML prepared: %s (%d internal links)" % (html_path, internal_links))

    html_to_pdf(html_path, output_path)
    pages = overlay_header_and_footer(output_path)
    validate_pdf(output_path)
    print("PDF ready: %s (%d pages, %.1f MB)" % (output_path, pages, output_path.stat().st_size / 1_048_576))

    if not args.keep_html:
        html_path.unlink(missing_ok=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("PDF generation failed: %s" % exc, file=sys.stderr)
        raise
