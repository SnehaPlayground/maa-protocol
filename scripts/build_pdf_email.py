#!/usr/bin/env python3
"""Primeidea PDF Report Builder — Email Template Edition"""
import argparse, os, sys

try:
    import weasyprint
except ImportError:
    print("ERROR: weasyprint not installed.")
    sys.exit(1)

LOGO_PATH = "/root/.openclaw/workspace/assets/assets/primeidea-logo.jpg"
LOGO_B64 = ""
if os.path.exists(LOGO_PATH):
    import base64
    LOGO_B64 = base64.b64encode(open(LOGO_PATH, 'rb').read()).decode()

# ── Print-optimised CSS ─────────────────────────────────────────────────────
PRINT_CSS = f"""
* {{ margin:0; padding:0; box-sizing:border-box; }}
@page {{
  size: A4;
  margin: 1.8cm 2cm 2cm 2.5cm;
  @top-left {{
    content: "";
    width: 36px; height: 36px;
    background: transparent url("data:image/jpeg;base64,{LOGO_B64}") no-repeat left center;
    background-size: contain;
  }}
}}
body {{
  font-family: 'Segoe UI','Helvetica Neue',Arial,sans-serif;
  background: #f4f6f9;
  color: #1a1a2e;
  font-size: 13px;
  line-height: 1.55;
}}

/* ── PAGE BREAK CONTROL ── */
.section {{ page-break-inside: avoid; page-break-before: auto; page-break-after: avoid; }}
h2 {{ page-break-after: avoid; }}
table {{ page-break-inside: avoid; }}
tr {{ page-break-inside: avoid; }}
.expert-card {{ page-break-inside: avoid; }}
.tldr {{ page-break-inside: avoid; }}
.highlight-box {{ page-break-inside: avoid; }}
.card {{ page-break-inside: avoid; }}

.email-wrapper {{
  max-width: 720px; margin: 0 auto;
  background: #ffffff;
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 4px 20px rgba(0,0,0,0.08);
}}

.header {{
  background: linear-gradient(135deg,#001f3f 0%,#003b6f 100%);
  color: #fff; padding: 24px 32px;
}}
.header .tag {{ font-size: 10px; letter-spacing: 2px; text-transform: uppercase; color: #a8d4ff; margin-bottom: 6px; }}
.header h1 {{ font-size: 20px; font-weight: 700; color: #fff; margin-bottom: 2px; }}
.header .date-line {{ font-size: 11px; color: #a8d4ff; margin-top: 4px; }}

.market-bar {{
  background: #0a1628; padding: 10px 28px;
  display: flex; gap: 20px; flex-wrap: wrap; align-items: center;
}}
.market-item {{ text-align: center; }}
.market-item .label {{ font-size: 9px; color: #7a9bb5; text-transform: uppercase; letter-spacing: 1px; }}
.market-item .value {{ font-size: 14px; font-weight: 700; color: #fff; }}
.market-item .change {{ font-size: 10px; font-weight: 600; }}
.up {{ color: #00c853; }}
.down {{ color: #ff5252; }}
.flat {{ color: #ffb300; }}

.content {{ padding: 20px 32px; }}

.holiday-banner {{
  background: #fff3cd; border: 1px solid #ffc107; border-radius: 6px;
  padding: 10px 16px; margin-bottom: 16px; font-size: 12px;
  color: #856404; text-align: center;
}}

.tldr {{
  background: linear-gradient(135deg,#e8f4fd 0%,#f0f7ff 100%);
  border-left: 5px solid #001f3f; border-radius: 6px;
  padding: 14px 18px; margin-bottom: 20px;
}}
.tldr p {{ font-size: 13px; color: #1a1a2e; line-height: 1.65; }}

.section {{ margin-bottom: 20px; }}
.section h2 {{
  font-size: 13px; font-weight: 700; color: #001f3f;
  text-transform: uppercase; letter-spacing: 1px;
  border-bottom: 2px solid #001f3f; padding-bottom: 5px;
  margin-bottom: 10px;
}}
.section p {{ font-size: 12.5px; color: #3a3a5a; margin-bottom: 7px; line-height: 1.55; }}

.bullet-list {{ list-style: none; padding: 0; margin-bottom: 10px; }}
.bullet-list li {{ padding: 4px 0 4px 18px; position: relative; font-size: 12.5px; color: #3a3a5a; line-height: 1.5; }}
.bullet-list li::before {{ content: '▸'; position: absolute; left: 0; color: #001f3f; font-weight: 700; }}

.highlight-box {{
  background: #fff8e1; border: 1px solid #ffe082; border-radius: 6px;
  padding: 10px 14px; margin-bottom: 10px;
}}
.highlight-box p {{ font-size: 12px; color: #3a3a5a; margin-bottom: 4px; }}

.table-wrap {{ overflow-x: auto; margin-bottom: 12px; }}
table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
th {{
  background: #001f3f; color: #fff; padding: 7px 10px;
  text-align: left; font-weight: 600; font-size: 11.5px;
}}
td {{ padding: 6px 10px; border-bottom: 1px solid #e5e5e5; font-size: 12px; }}
tr:nth-child(even) td {{ background: #f8f9fc; }}
tr:last-child td {{ border-bottom: none; }}
tr {{ page-break-inside: avoid; }}

.up-text {{ color: #00c853; font-weight: 600; }}
.down-text {{ color: #ff5252; font-weight: 600; }}
.neutral-text {{ color: #ffb300; font-weight: 600; }}

.expert-card {{
  background: #f8f9fc; border: 1px solid #e0e5f0; border-radius: 6px;
  padding: 12px 14px; margin-bottom: 8px;
}}
.expert-card .expert-name {{ font-size: 12px; font-weight: 700; color: #001f3f; margin-bottom: 1px; }}
.expert-card .expert-title {{ font-size: 10.5px; color: #7a8aa0; margin-bottom: 6px; }}
.expert-card p {{ font-size: 12px; color: #3a3a5a; margin-bottom: 5px; }}

.cta-block {{
  margin-top: 14px; padding: 12px 14px; background: #001f3f; border-radius: 8px; text-align: center;
}}
.cta-block .cta-title {{ font-size: 13px; font-weight: 700; color: #fff; margin: 0 0 4px; }}
.cta-block .cta-body {{ font-size: 12px; color: #a8d4ff; margin: 0; }}
.cta-block .cta-body strong {{ color: #fff; }}

.disclaimer {{
  background: #f0f4f8; border-radius: 6px; padding: 8px 12px;
  font-size: 10.5px; color: #7a8aa0; margin-top: 8px;
}}

.footer {{
  margin-top: 30px; padding: 18px 32px 20px; border-top: 1px solid #e5e5e5; font-size: 12px; color: #666;
}}
.footer .sig-line {{ font-weight: 600; color: #1a1a2e; margin-bottom: 4px; }}
.footer .sig-title {{ font-size: 11px; color: #001f3f; margin-bottom: 3px; }}
.footer .sig-firm {{ font-size: 11px; color: #003b6f; font-weight: 700; margin-bottom: 6px; }}
.footer .legal {{ margin-top: 10px; font-size: 10.5px; color: #999; line-height: 1.5; }}

.tag-red {{ background: #ff5252; color: #fff; font-size: 9px; padding: 2px 6px; border-radius: 10px; font-weight: 700; letter-spacing: 0.5px; margin-left: 5px; }}
.tag-orange {{ background: #ff9800; color: #fff; font-size: 9px; padding: 2px 6px; border-radius: 10px; font-weight: 700; letter-spacing: 0.5px; margin-left: 5px; }}
.tag-blue {{ background: #1976d2; color: #fff; font-size: 9px; padding: 2px 6px; border-radius: 10px; font-weight: 700; letter-spacing: 0.5px; margin-left: 5px; }}
.tag-gray {{ background: #78909c; color: #fff; font-size: 9px; padding: 2px 6px; border-radius: 10px; font-weight: 700; letter-spacing: 0.5px; margin-left: 5px; }}

@media(max-width:600px) {{
  .content, .header {{ padding: 16px; }}
  .market-bar {{ padding: 8px 16px; gap: 14px; }}
  table {{ font-size: 11px; }} th, td {{ padding: 5px 7px; }}
}}
"""

def inject_print_css(html_content):
    """Inject print CSS into an existing HTML document's <head>."""
    # Find </head> and insert CSS before it
    close_head = html_content.find('</head>')
    if close_head == -1:
        # No </head> found — prepend to body
        body_start = html_content.find('<body')
        if body_start == -1:
            return html_content
        insert_pos = html_content.find('>', body_start) + 1
    else:
        insert_pos = close_head

    style_block = f"\n<style type=\"text/css\">\n{PRINT_CSS}\n</style>\n"
    return html_content[:insert_pos] + style_block + html_content[insert_pos:]

def main():
    parser = argparse.ArgumentParser(description="Primeidea PDF Builder (Email Template)")
    parser.add_argument('--input', '-i', required=True, help="Input HTML file")
    parser.add_argument('--output', '-o', required=True, help="Output PDF file")
    parser.add_argument('--title', '-t', default="Primeidea Report")
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"ERROR: Input not found: {args.input}")
        sys.exit(1)

    raw = open(args.input).read()

    # Inject print CSS
    html = inject_print_css(raw)

    # Override title
    if args.title and args.title != "Primeidea Report":
        html = html.replace('<title>', f'<title>{args.title}</title><original-title>', 1)

    tmp = args.output + '.tmp.html'
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(html)

    import warnings
    warnings.filterwarnings('ignore')

    try:
        weasyprint.HTML(filename=tmp, encoding='utf-8').write_pdf(args.output)
    except Exception as e:
        print(f"ERROR: PDF generation failed: {e}")
        os.remove(tmp)
        sys.exit(1)

    os.remove(tmp)
    size_kb = os.path.getsize(args.output) / 1024
    print(f"PDF created: {args.output} ({size_kb:.1f} KB)")

if __name__ == '__main__':
    main()
