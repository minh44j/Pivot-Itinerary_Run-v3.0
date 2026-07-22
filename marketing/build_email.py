#!/usr/bin/env python3
"""Assemble the Pivot intro sales email (concise premium edition).
Run: python3 marketing/build_email.py   (from repo root)."""
import base64, io, os
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def logo_data_uri(width=200):
    img = Image.open(os.path.join(ROOT, "logo.png")).convert("RGBA")
    w, h = img.size
    img = img.resize((width, int(h * width / w)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

LOGO = logo_data_uri()

# ---- contact / person data ---------------------------------------------------
SENDER_NAME   = "Hashil Muhammed"
SENDER_TITLE  = "Business Development Executive"
SENDER_EMAIL  = "hashil@pivot-travels.com"
SENDER_MOBILE = "+966 57 367 9436"
SENDER_TEL    = "+966 11 220 0296"
SENDER_EXT    = "121"
WHATSAPP      = "https://wa.me/966573679436"
SALES_EMAIL   = "sales@pivot-travels.com"
WEBSITE       = "https://www.pivot-travels.com"

TEL_M = SENDER_MOBILE.replace(" ", "")
TEL_O = SENDER_TEL.replace(" ", "")

# Featured transport services -> concise two-column list (name + 3-word tag)
services = [
    ("Executive Chauffeur",  "Discreet, trained drivers"),
    ("Airport Transfers",    "Flight-tracked, meet &amp; greet"),
    ("VIP &amp; Delegates",  "First-class movement"),
    ("Event Fleets",         "Exhibitions &amp; conferences"),
    ("Staff &amp; Crew",     "Scheduled shuttles"),
    ("Coaches &amp; Buses",  "Group travel at scale"),
]
def cell(name, tag):
    return f"""
                  <td class="stack stack-pad" width="50%" valign="top" style="padding:11px 14px;">
                    <div style="border-left:2px solid #c9a84c; padding-left:12px;">
                      <div style="font-family:Arial,Helvetica,sans-serif; font-size:15px; font-weight:bold; color:#ffffff;">{name}</div>
                      <div style="font-family:Arial,Helvetica,sans-serif; font-size:12px; color:#a2a2a6; margin-top:2px;">{tag}</div>
                    </div>
                  </td>"""
svc_rows = ""
for i in range(0, len(services), 2):
    svc_rows += "\n                <tr>" + cell(*services[i]) + cell(*services[i+1]) + "\n                </tr>"

HTML = f"""<!--
  Pivot Travel Management - Introductory Sales Email (concise premium edition)
  ---------------------------------------------------------------------------
  USE: open in a browser, Ctrl+A, Ctrl+C, then paste into a new Outlook email.
  EDIT: change copy/contacts at the top of marketing/build_email.py, then re-run it.
-->
<!DOCTYPE html>
<html lang="en" xmlns="http://www.w3.org/1999/xhtml" xmlns:v="urn:schemas-microsoft-com:vml" xmlns:o="urn:schemas-microsoft-com:office:office">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="X-UA-Compatible" content="IE=edge">
  <meta name="x-apple-disable-message-reformatting">
  <title>Pivot Travel Management</title>
  <!--[if mso]><noscript><xml><o:OfficeDocumentSettings><o:PixelsPerInch>96</o:PixelsPerInch><o:AllowPNG/></o:OfficeDocumentSettings></xml></noscript><![endif]-->
  <style>
    body, table, td, a {{ -webkit-text-size-adjust:100%; -ms-text-size-adjust:100%; }}
    table, td {{ mso-table-lspace:0pt; mso-table-rspace:0pt; }}
    img {{ -ms-interpolation-mode:bicubic; border:0; height:auto; line-height:100%; outline:none; text-decoration:none; }}
    table {{ border-collapse:collapse !important; }}
    body {{ margin:0 !important; padding:0 !important; width:100% !important; }}
    a {{ text-decoration:none; }}
    @media screen and (max-width:600px) {{
      .container {{ width:100% !important; }}
      .px {{ padding-left:26px !important; padding-right:26px !important; }}
      .stack {{ display:block !important; width:100% !important; }}
      .stack-pad {{ padding-bottom:6px !important; }}
      .h1 {{ font-size:32px !important; line-height:38px !important; }}
      .hero-pad {{ padding:48px 26px !important; }}
    }}
  </style>
</head>
<body style="margin:0; padding:0; background-color:#0e0e0f;">
  <div style="display:none; font-size:1px; color:#0e0e0f; line-height:1px; max-height:0; max-width:0; opacity:0; overflow:hidden; mso-hide:all;">
    Executive event transportation, handled flawlessly &mdash; from a single luxury arrival to a full delegate fleet.
  </div>

  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#0e0e0f;">
    <tr>
      <td align="center" style="padding:26px 12px;">
        <table role="presentation" class="container" width="600" cellpadding="0" cellspacing="0" border="0" style="width:600px; max-width:600px; background-color:#111113; border-radius:16px; overflow:hidden; box-shadow:0 20px 60px rgba(0,0,0,0.5);">

          <!-- HEADER -->
          <tr>
            <td align="center" bgcolor="#161618" style="padding:26px 30px 20px 30px;">
              <img src="{LOGO}" alt="Pivot Travel Management" width="76" style="display:block; width:76px; max-width:76px; height:auto; margin:0 auto 10px auto;">
              <div style="font-family:Georgia,'Times New Roman',serif; font-size:17px; letter-spacing:1px; color:#ffffff;">Pivot&nbsp;Travel&nbsp;Management</div>
              <div style="font-family:Arial,Helvetica,sans-serif; font-size:9px; letter-spacing:3px; color:#c9a84c; text-transform:uppercase; margin-top:5px;">Corporate Travel &amp; Executive Transportation</div>
            </td>
          </tr>

          <!-- HERO -->
          <tr>
            <td align="center" class="hero-pad" bgcolor="#141416" style="background:linear-gradient(160deg,#26262a 0%,#141416 62%,#0e0e0f 100%); padding:60px 46px 54px 46px;">
              <div style="font-family:Arial,Helvetica,sans-serif; font-size:11px; letter-spacing:4px; color:#c9a84c; text-transform:uppercase; margin-bottom:20px;">Executive Event Transportation</div>
              <div class="h1" style="font-family:Georgia,'Times New Roman',serif; font-size:42px; line-height:48px; color:#ffffff; margin:0 0 20px 0;">Arrivals worth<br>remembering.</div>
              <div style="font-family:Arial,Helvetica,sans-serif; font-size:16px; line-height:26px; color:#c2c2c6; max-width:400px; margin:0 auto 34px auto;">
                Chauffeur-driven service that makes transportation the one thing you never have to think about.
              </div>
              <table role="presentation" cellpadding="0" cellspacing="0" border="0" align="center"><tr>
                <td align="center" bgcolor="#c9a84c" style="border-radius:7px;">
                  <!--[if mso]><v:roundrect xmlns:v="urn:schemas-microsoft-com:vml" xmlns:w="urn:schemas-microsoft-com:office:word" href="mailto:{SENDER_EMAIL}" style="height:52px;v-text-anchor:middle;width:250px;" arcsize="14%" strokecolor="#c9a84c" fillcolor="#c9a84c"><w:anchorlock/><center style="color:#141416;font-family:Arial,sans-serif;font-size:14px;font-weight:bold;letter-spacing:1px;">REQUEST A PROPOSAL</center></v:roundrect><![endif]-->
                  <!--[if !mso]><!-- --><a href="mailto:{SENDER_EMAIL}" style="display:inline-block; font-family:Arial,Helvetica,sans-serif; font-size:14px; font-weight:bold; letter-spacing:1px; color:#141416; padding:17px 42px; border-radius:7px; background-color:#c9a84c;">REQUEST&nbsp;A&nbsp;PROPOSAL</a><!--<![endif]-->
                </td>
              </tr></table>
            </td>
          </tr>

          <!-- SERVICES (featured, dark, concise) -->
          <tr>
            <td class="px" style="padding:42px 40px 6px 40px;">
              <div style="font-family:Arial,Helvetica,sans-serif; font-size:11px; letter-spacing:3px; color:#c9a84c; text-transform:uppercase; text-align:center; margin-bottom:6px;">Our Signature Service</div>
              <div style="font-family:Georgia,'Times New Roman',serif; font-size:25px; color:#ffffff; text-align:center;">Executive Ground Transportation</div>
            </td>
          </tr>
          <tr>
            <td class="px" style="padding:20px 26px 8px 26px;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">{svc_rows}
              </table>
            </td>
          </tr>

          <!-- FLEET line -->
          <tr>
            <td class="px" align="center" style="padding:18px 40px 34px 40px;">
              <div style="font-family:Arial,Helvetica,sans-serif; font-size:14px; color:#8f8f94; letter-spacing:1px;">
                <span style="color:#ffffff;">Sedans</span> &nbsp;&middot;&nbsp; <span style="color:#ffffff;">SUVs</span> &nbsp;&middot;&nbsp; <span style="color:#ffffff;">Luxury Vans</span> &nbsp;&middot;&nbsp; <span style="color:#ffffff;">Minibuses</span> &nbsp;&middot;&nbsp; <span style="color:#ffffff;">Coaches</span>
              </div>
              <div style="font-family:Arial,Helvetica,sans-serif; font-size:12px; color:#6f6f74; margin-top:8px;">One fleet, matched to any event &mdash; from a single arrival to a full delegation.</div>
            </td>
          </tr>

          <!-- PORTFOLIO strip -->
          <tr>
            <td bgcolor="#161618" style="padding:24px 44px 26px 44px; border-top:1px solid #232326;">
              <div style="font-family:Arial,Helvetica,sans-serif; font-size:10px; letter-spacing:3px; color:#c9a84c; text-transform:uppercase; text-align:center; margin-bottom:10px;">A Full-Service Travel Partner</div>
              <div style="font-family:Arial,Helvetica,sans-serif; font-size:13px; line-height:24px; color:#b6b6ba; text-align:center;">
                Air Ticketing &nbsp;&middot;&nbsp; Corporate Travel &nbsp;&middot;&nbsp; Hotels &nbsp;&middot;&nbsp; Visa Assistance &nbsp;&middot;&nbsp; Travel Insurance &nbsp;&middot;&nbsp; Holidays &nbsp;&middot;&nbsp; Umrah &amp; Hajj &nbsp;&middot;&nbsp; MICE &amp; Events
              </div>
            </td>
          </tr>

          <!-- SIGNATURE + CTA -->
          <tr>
            <td class="px" style="padding:34px 44px 30px 44px;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <td valign="top">
                    <div style="font-family:Georgia,'Times New Roman',serif; font-size:19px; color:#ffffff;">{SENDER_NAME}</div>
                    <div style="font-family:Arial,Helvetica,sans-serif; font-size:11px; letter-spacing:1px; color:#c9a84c; text-transform:uppercase; margin-top:3px;">{SENDER_TITLE}</div>
                    <div style="font-family:Arial,Helvetica,sans-serif; font-size:13px; line-height:22px; color:#a2a2a6; margin-top:12px;">
                      <a href="tel:{TEL_M}" style="color:#d8d8dc;">{SENDER_MOBILE}</a> &nbsp;<span style="color:#5f5f64;">mobile</span><br>
                      <a href="tel:{TEL_O}" style="color:#d8d8dc;">{SENDER_TEL}</a>, Ext. {SENDER_EXT}<br>
                      <a href="mailto:{SENDER_EMAIL}" style="color:#d8d8dc;">{SENDER_EMAIL}</a>
                    </div>
                    <table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin-top:16px;"><tr>
                      <td align="center" bgcolor="#c9a84c" style="border-radius:6px;">
                        <a href="{WHATSAPP}" style="display:inline-block; font-family:Arial,Helvetica,sans-serif; font-size:12px; font-weight:bold; letter-spacing:1px; color:#141416; padding:12px 26px; border-radius:6px; background-color:#c9a84c;">CHAT ON WHATSAPP</a>
                      </td>
                    </tr></table>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- FOOTER -->
          <tr>
            <td bgcolor="#0c0c0d" style="padding:24px 44px 26px 44px; border-top:1px solid #232326;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr><td align="center">
                <div style="font-family:Georgia,'Times New Roman',serif; font-size:14px; letter-spacing:1px; color:#e6e6e8; margin-bottom:8px;">Pivot&nbsp;Travel&nbsp;Management</div>
                <div style="font-family:Arial,Helvetica,sans-serif; font-size:11px; line-height:18px; color:#7a7a7f;">
                  Suite 20, 2nd Floor, Mobco Building, 2762 Ibn Al Anbari Street, Al Amal District, Riyadh, KSA &nbsp;&middot;&nbsp; CR 7043148696
                </div>
                <div style="margin-top:12px; font-family:Arial,Helvetica,sans-serif; font-size:11px;">
                  <a href="mailto:{SALES_EMAIL}" style="color:#c9a84c; padding:0 7px;">{SALES_EMAIL}</a><span style="color:#333336;">|</span>
                  <a href="{WEBSITE}" style="color:#c9a84c; padding:0 7px;">www.pivot-travels.com</a>
                </div>
                <div style="font-family:Arial,Helvetica,sans-serif; font-size:10px; color:#4d4d52; margin-top:16px;">&copy; 2026 Pivot Travel Management</div>
              </td></tr></table>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""

out = os.path.join(ROOT, "marketing", "intro_sales_email.html")
open(out, "w").write(HTML)
print("wrote", out, "|", round(len(HTML)/1024), "KB")
