#!/usr/bin/env python3
"""
Primeidea PDF Report Builder
Usage: python3 build_pdf_report.py --input <file.md or file.html> --output <file.pdf>
"""
import argparse
import base64
import os
import re
import warnings

try:
    import weasyprint
except ImportError:
    print("ERROR: weasyprint not installed. Run: pip install weasyprint")
    exit(1)

LOGO_PATH = "/root/.openclaw/workspace/assets/assets/primeidea-logo.jpg"

# ─── Markdown → HTML ─────────────────────────────────────────────────────────

def md_to_html(text: str) -> str:
    lines = text.split('\n')
    html = []
    in_ul = False
    i = 0
    while i < len(lines):
        line = lines[i]

        # Skip markdown HRs
        if re.match(r'^---+$', line.strip()):
            i += 1
            continue

        # H1
        if line.startswith('# '):
            if in_ul:
                html.append('  </ul>')
                in_ul = False
            html.append(f'<h1 style="font-size:22px;font-weight:700;color:#1a1a2e;margin:0 0 16px;padding-bottom:8px;border-bottom:3px solid #e94560;display:inline-block;">{line[2:].strip()}</h1>')

        # H2
        elif line.startswith('## '):
            if in_ul:
                html.append('  </ul>')
                in_ul = False
            html.append(f'<h2 style="font-size:16px;font-weight:700;color:#1a1a2e;margin:28px 0 12px;padding-bottom:6px;border-bottom:2px solid #e94560;display:inline-block;">{line[3:].strip()}</h2>')

        # H3
        elif line.startswith('### '):
            if in_ul:
                html.append('  </ul>')
                in_ul = False
            html.append(f'<h3 style="font-size:14px;font-weight:700;color:#16213e;margin:20px 0 8px;">{line[4:].strip()}</h3>')

        # Table
        elif line.strip().startswith('|'):
            if in_ul:
                html.append('  </ul>')
                in_ul = False
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith('|'):
                table_lines.append(lines[i].strip())
                i += 1
            i -= 1
            rows_data = []
            for tline in table_lines:
                if re.match(r'^\|[\s\-:|]+\|$', tline):
                    continue
                cols = [c.strip() for c in tline.split('|') if c.strip() != '']
                rows_data.append(cols)
            if rows_data:
                html.append('<table style="width:100%;border-collapse:collapse;font-size:13px;margin:10px 0;">')
                for ri, row in enumerate(rows_data):
                    tag = 'th' if ri == 0 else 'td'
                    bg = '#1a1a2e' if ri == 0 else ('#f8f9fb' if ri % 2 == 1 else '#ffffff')
                    color = '#ffffff' if ri == 0 else '#1a1a2e'
                    html.append('  <tr>')
                    for col in row:
                        bold = 'font-weight:700;' if ri == 0 else ''
                        html.append(f'    <{tag} style="padding:8px 12px;border-bottom:1px solid #eee;background:{bg};color:{color};{bold}">{col}</{tag}>')
                    html.append('  </tr>')
                html.append('</table>')

        # Bullet
        elif line.strip().startswith('- '):
            if not in_ul:
                html.append('<ul style="margin:8px 0;padding-left:20px;">')
                in_ul = True
            content = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', line.strip()[2:])
            html.append(f'  <li style="margin-bottom:4px;font-size:13px;line-height:1.5;">{content}</li>')

        # Blank
        elif line.strip() == '':
            if in_ul:
                html.append('  </ul>')
                in_ul = False
            html.append('<div style="height:6px;"></div>')

        # Paragraph
        else:
            if in_ul:
                html.append('  </ul>')
                in_ul = False
            content = re.sub(r'\*\*(.+?)\*\*', r'<strong style="color:#e94560;">\1</strong>', line.strip())
            html.append(f'<p style="font-size:13px;line-height:1.6;margin:6px 0;">{content}</p>')

        i += 1

    if in_ul:
        html.append('  </ul>')

    return '\n'.join(html)


# ─── Build Full HTML Document ─────────────────────────────────────────────────

def build_html(body_content: str, title: str = "Primeidea Report") -> str:
    logo_b64 = base64.b64encode(open(LOGO_PATH, 'rb').read()).decode()

    css = f"""
* {{ margin:0; padding:0; box-sizing:border-box; }}
@page {{
  size: A4;
  margin: 2cm 2cm 2cm 2.5cm;
  @top-left {{
    content: "";
    width: 40px;
    height: 40px;
    background: transparent url("data:image/jpeg;base64,{logo_b64}") no-repeat left center;
    background-size: contain;
  }}
}}
body {{
  font-family:'Segoe UI',Arial,sans-serif;
  background:#f4f6f9;
  color:#1a1a2e;
  font-size:14px;
  line-height:1.5;
  padding:20px;
}}
.email-wrapper {{
  max-width:720px;
  margin:0 auto;
  background:#ffffff;
  border-radius:8px;
  overflow:hidden;
  box-shadow:0 4px 20px rgba(0,0,0,0.08);
}}
.header {{
  background:linear-gradient(135deg,#1a1a2e 0%,#16213e 100%);
  color:#fff;
  padding:28px 36px;
}}
.header .tag {{
  background:#e94560;
  display:inline-block;
  padding:3px 10px;
  border-radius:4px;
  font-size:11px;
  font-weight:700;
  letter-spacing:1px;
  margin-bottom:10px;
}}
.header h1 {{
  font-size:20px;
  font-weight:700;
  margin-bottom:4px;
}}
.header .date {{
  opacity:0.7;
  font-size:13px;
}}
.tldr {{
  background:#0f3460;
  color:#fff;
  padding:20px 36px;
}}
.tldr h2 {{
  font-size:12px;
  text-transform:uppercase;
  letter-spacing:1.5px;
  opacity:0.7;
  margin-bottom:10px;
}}
.tldr p {{
  font-size:13px;
  line-height:1.7;
  margin-bottom:6px;
}}
.tldr strong {{
  color:#e94560;
}}
.section {{
  padding:24px 36px;
  border-bottom:1px solid #eee;
}}
.section:last-child {{
  border-bottom:none;
}}
.section h2 {{
  font-size:15px;
  font-weight:700;
  color:#1a1a2e;
  margin-bottom:14px;
  padding-bottom:8px;
  border-bottom:2px solid #e94560;
  display:inline-block;
}}
.card {{
  background:#f8f9fb;
  border-left:4px solid #e94560;
  padding:16px 20px;
  margin-bottom:14px;
  border-radius:0 6px 6px 0;
}}
.card h3 {{
  font-size:14px;
  font-weight:700;
  margin-bottom:4px;
  color:#1a1a2e;
}}
.card .meta {{
  font-size:12px;
  color:#666;
  margin-bottom:8px;
}}
.card p {{
  font-size:13px;
  margin-bottom:6px;
}}
.card ul {{
  margin:6px 0 6px 18px;
}}
.card li {{
  font-size:13px;
  margin-bottom:4px;
}}
.label {{
  display:inline-block;
  padding:2px 8px;
  border-radius:4px;
  font-size:11px;
  font-weight:700;
  margin-left:8px;
  vertical-align:middle;
}}
.label-approval {{ background:#00c853; color:#fff; }}
.label-pilot {{ background:#2979ff; color:#fff; }}
.label-validation {{ background:#ff9800; color:#fff; }}
.label-reject {{ background:#e0e0e0; color:#666; }}
.actions {{
  padding:24px 36px;
  background:#f8f9fb;
}}
.actions h2 {{
  font-size:15px;
  font-weight:700;
  color:#1a1a2e;
  margin-bottom:14px;
}}
.action-col {{
  width:33.33%;
  vertical-align:top;
  display:inline-block;
}}
.action-col h3 {{
  font-size:12px;
  font-weight:700;
  text-transform:uppercase;
  letter-spacing:1px;
  margin-bottom:10px;
  padding:6px 12px;
  border-radius:4px;
}}
.action-today h3 {{ background:#00c853; color:#fff; }}
.action-week h3 {{ background:#2979ff; color:#fff; }}
.action-later h3 {{ background:#ff9800; color:#fff; }}
.action-col ul {{
  list-style:none;
  padding:0 12px;
}}
.action-col li {{
  font-size:12px;
  margin-bottom:6px;
  padding-left:14px;
  position:relative;
}}
.action-col li:before {{
  content:'\\2192';
  position:absolute;
  left:0;
  color:#e94560;
}}
.exec-summary-table {{
  width:100%;
  border-collapse:collapse;
  font-size:12px;
  margin-top:10px;
}}
.exec-summary-table th {{
  background:#1a1a2e;
  color:#fff;
  padding:8px 12px;
  text-align:left;
}}
.exec-summary-table td {{
  padding:7px 12px;
  border-bottom:1px solid #eee;
}}
.exec-summary-table tr:nth-child(even) td {{
  background:#f8f9fb;
}}
.footer {{
  background:#f4f6f9;
  padding:16px 36px;
  text-align:center;
  font-size:11px;
  color:#999;
}}
@media(max-width:600px) {{
  .action-col {{ width:100%; margin-bottom:16px; }}
  .header,.tldr,.section,.actions {{ padding:16px; }}
}}
"""

    return f"<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n<meta charset=\"UTF-8\">\n<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">\n<title>{title}</title>\n<style>{css}</style>\n</head>\n<body>\n{body_content}\n</body>\n</html>"


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Primeidea PDF Report Builder")
    parser.add_argument('--input', '-i', required=True, help="Input .md or .html file")
    parser.add_argument('--output', '-o', required=True, help="Output PDF file path")
    parser.add_argument('--title', '-t', default="Primeidea Report", help="Document title")
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"ERROR: Input file not found: {args.input}")
        exit(1)

    if not os.path.exists(LOGO_PATH):
        print(f"ERROR: Logo not found: {LOGO_PATH}")
        exit(1)

    raw = open(args.input).read()

    # Detect if HTML or Markdown
    if args.input.endswith('.html') or raw.strip().startswith('<!DOCTYPE') or raw.strip().startswith('<html'):
        body = raw
    else:
        body = md_to_html(raw)

    full_html = build_html(body, title=args.title)

    # Write temp HTML for weasyprint
    tmp_html = args.output + '.tmp.html'
    with open(tmp_html, 'w') as f:
        f.write(full_html)

    warnings.filterwarnings('ignore')
    try:
        weasyprint.HTML(filename=tmp_html).write_pdf(args.output)
    except Exception as e:
        print(f"ERROR: PDF generation failed: {e}")
        os.remove(tmp_html)
        exit(1)

    os.remove(tmp_html)

    size_kb = os.path.getsize(args.output) / 1024
    print(f"PDF created: {args.output} ({size_kb:.1f} KB)")


if __name__ == '__main__':
    main()
