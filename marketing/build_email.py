#!/usr/bin/env python3
"""Assemble the Pivot intro sales email with the repo logo embedded as base64.
Run: python3 marketing/build_email.py  (from repo root)
Regenerate whenever logo.png or the copy changes."""
import base64, io, os
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def logo_data_uri(width=320):
    img = Image.open(os.path.join(ROOT, "logo.png")).convert("RGBA")
    w, h = img.size
    img = img.resize((width, int(h * width / w)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

LOGO = logo_data_uri()

# ---- editable contact / person data ------------------------------------------
SENDER_NAME   = "Hashil Muhammed"
SENDER_TITLE  = "Business Development Executive"
SENDER_DEPT   = "Sales &amp; Marketing"
SENDER_EMAIL  = "hashil@pivot-travels.com"
SENDER_MOBILE = "+966 57 367 9436"
SENDER_TEL    = "+966 11 220 0296"
SENDER_EXT    = "121"
WHATSAPP      = "https://wa.me/966573679436"      # from mobile number
SALES_EMAIL   = "sales@pivot-travels.com"
WEBSITE       = "https://www.pivot-travels.com"

def svc(icon, title, desc):
    return f"""
                  <td class="stack stack-pad" width="50%" valign="top" style="padding:12px;">
                    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
                      <tr><td valign="top" width="60">
                        <div class="svc-icon" style="width:52px; height:52px; line-height:52px; text-align:center; background:#f4efe1; border-radius:50%; font-size:24px; color:#c9a84c;">{icon}</div>
                      </td>
                      <td valign="top" style="padding-left:14px;">
                        <div style="font-family:Arial,Helvetica,sans-serif; font-size:15px; font-weight:bold; color:#1e1e20; margin-bottom:4px;">{title}</div>
                        <div style="font-family:Arial,Helvetica,sans-serif; font-size:13px; line-height:20px; color:#6a6a6e;">{desc}</div>
                      </td></tr>
                    </table>
                  </td>"""

# Highlighted (transportation) sub-services -- the FEATURED offering
transport = [
    ("&#128666;", "Executive Chauffeur",       "Professionally trained drivers, discreet and impeccably presented."),
    ("&#9992;",   "Airport Transfers",          "Flight-tracked pickups with meet &amp; greet &mdash; never a wait."),
    ("&#11088;",  "VIP Transportation",         "First-class movement for delegates, speakers and dignitaries."),
    ("&#127881;", "Event Transportation",       "Fully coordinated fleets for exhibitions and conferences."),
    ("&#128101;", "Staff Transportation",       "Reliable scheduled shuttles for crews and personnel."),
    ("&#128652;", "Corporate Bus &amp; Coach",  "Group movement at scale, on time, every time."),
]
transport_rows = ""
for i in range(0, len(transport), 2):
    transport_rows += "\n                <tr>" + svc(*transport[i]) + svc(*transport[i+1]) + "\n                </tr>"

# Full core-services portfolio chips
portfolio = [
    ("&#128666;", "Executive Transportation", True),
    ("&#127903;", "Air Ticketing &amp; Reservations", False),
    ("&#128188;", "Corporate Travel Management", False),
    ("&#127976;", "Hotel &amp; Accommodation", False),
    ("&#128196;", "Visa Assistance", False),
    ("&#128737;", "Travel Insurance", False),
    ("&#127796;", "Holiday &amp; Leisure Packages", False),
    ("&#128331;", "Umrah &amp; Hajj", False),
    ("&#127942;", "MICE &amp; Events", False),
]
def chip(icon, label, featured):
    if featured:
        bg = "background:#c9a84c;"
        col = "color:#1e1e20;"
        tag = '<span style="font-family:Arial,sans-serif; font-size:8px; letter-spacing:1px; color:#1e1e20; background:rgba(255,255,255,0.55); border-radius:8px; padding:1px 6px; margin-left:6px; vertical-align:middle;">FEATURED</span>'
    else:
        bg = "background:#26262a; border:1px solid #3a3a3e;"
        col = "color:#e6e6e8;"
        tag = ""
    return f"""
                    <td valign="top" style="padding:6px;">
                      <div style="{bg} border-radius:10px; padding:12px 14px; font-family:Arial,Helvetica,sans-serif;">
                        <span style="font-size:17px;">{icon}</span>
                        <span style="font-size:13px; font-weight:bold; {col} padding-left:6px;">{label}</span>{tag}
                      </div>
                    </td>"""
portfolio_rows = ""
for i in range(0, len(portfolio), 2):
    row = chip(*portfolio[i])
    row += chip(*portfolio[i+1]) if i + 1 < len(portfolio) else '\n                    <td style="padding:6px;">&nbsp;</td>'
    portfolio_rows += "\n                  <tr>" + row + "\n                  </tr>"

HTML = f"""<!--
  PIVOT TRAVEL MANAGEMENT - Introductory Sales Email  (Chauffeur featured)
  ------------------------------------------------------------------------
  HOW TO USE:
    1. Open this file in a browser to preview.
    2. Select ALL (Ctrl+A), Copy (Ctrl+C), then paste into a new Outlook email.
       The logo is embedded, so the email is self-contained.

  ALREADY FILLED IN (real data):
    - Logo embedded from repo logo.png.
    - Full core-services portfolio listed; Executive Transportation FEATURED.
    - Salesperson signature: {SENDER_NAME}, {SENDER_TITLE}.
    - Contacts: mobile {SENDER_MOBILE} / office {SENDER_TEL} ext {SENDER_EXT} /
      {SENDER_EMAIL} / WhatsApp / {SALES_EMAIL} / {WEBSITE}.

  To change copy or the person, edit marketing/build_email.py and re-run it.
-->
<!DOCTYPE html>
<html lang="en" xmlns="http://www.w3.org/1999/xhtml" xmlns:v="urn:schemas-microsoft-com:vml" xmlns:o="urn:schemas-microsoft-com:office:office">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="X-UA-Compatible" content="IE=edge">
  <meta name="x-apple-disable-message-reformatting">
  <title>Pivot Travel Management</title>
  <!--[if mso]>
  <noscript><xml><o:OfficeDocumentSettings><o:PixelsPerInch>96</o:PixelsPerInch><o:AllowPNG/></o:OfficeDocumentSettings></xml></noscript>
  <![endif]-->
  <style>
    body, table, td, a {{ -webkit-text-size-adjust: 100%; -ms-text-size-adjust: 100%; }}
    table, td {{ mso-table-lspace: 0pt; mso-table-rspace: 0pt; }}
    img {{ -ms-interpolation-mode: bicubic; border: 0; height: auto; line-height: 100%; outline: none; text-decoration: none; }}
    table {{ border-collapse: collapse !important; }}
    body {{ margin: 0 !important; padding: 0 !important; width: 100% !important; }}
    a {{ text-decoration: none; }}
    @media screen and (max-width: 600px) {{
      .container {{ width: 100% !important; }}
      .px {{ padding-left: 24px !important; padding-right: 24px !important; }}
      .stack {{ display: block !important; width: 100% !important; }}
      .stack-pad {{ padding-bottom: 14px !important; }}
      .h1 {{ font-size: 30px !important; line-height: 36px !important; }}
      .hero-pad {{ padding: 44px 24px !important; }}
      .center-m {{ text-align: center !important; }}
      .svc-icon {{ width: 46px !important; height: 46px !important; line-height: 46px !important; font-size: 22px !important; }}
    }}
  </style>
</head>
<body style="margin:0; padding:0; background-color:#0e0e0f;">
  <div style="display:none; font-size:1px; color:#0e0e0f; line-height:1px; max-height:0; max-width:0; opacity:0; overflow:hidden; mso-hide:all;">
    Your preferred partner for executive event transportation &mdash; and complete corporate travel.
  </div>

  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#0e0e0f;">
    <tr>
      <td align="center" style="padding: 28px 12px;">
        <table role="presentation" class="container" width="600" cellpadding="0" cellspacing="0" border="0" style="width:600px; max-width:600px; background-color:#ffffff; border-radius:14px; overflow:hidden; box-shadow:0 18px 50px rgba(0,0,0,0.45);">

          <!-- HEADER -->
          <tr>
            <td align="center" bgcolor="#1e1e20" style="background:linear-gradient(180deg,#323234 0%,#1e1e20 55%,#151517 100%); padding: 30px 30px 22px 30px;">
              <img src="{LOGO}" alt="Pivot Travel Management" width="150" style="display:block; width:150px; max-width:150px; height:auto; margin:0 auto 12px auto;">
              <div style="font-family:Georgia,'Times New Roman',serif; font-size:21px; letter-spacing:3px; color:#ffffff;">PIVOT&nbsp;TRAVEL&nbsp;MANAGEMENT</div>
              <div style="height:2px; width:64px; background:#c9a84c; margin:14px auto 6px auto; line-height:2px; font-size:0;">&nbsp;</div>
              <div style="font-family:Arial,Helvetica,sans-serif; font-size:10px; letter-spacing:4px; color:#c9a84c; text-transform:uppercase;">Corporate Travel &amp; Executive Transportation</div>
            </td>
          </tr>

          <!-- HERO -->
          <tr>
            <td align="center" class="hero-pad" bgcolor="#151517" style="background:linear-gradient(160deg,#26262a 0%,#151517 60%,#0e0e0f 100%); padding: 54px 40px 50px 40px;">
              <div style="font-family:Arial,Helvetica,sans-serif; font-size:11px; letter-spacing:4px; color:#c9a84c; text-transform:uppercase; margin-bottom:18px;">The Preferred Transportation Partner</div>
              <div class="h1" style="font-family:Georgia,'Times New Roman',serif; font-size:38px; line-height:46px; color:#ffffff; margin:0 0 18px 0;">Transportation, handled&nbsp;flawlessly.</div>
              <div style="font-family:Arial,Helvetica,sans-serif; font-size:16px; line-height:26px; color:#c9c9cc; max-width:440px; margin:0 auto;">
                When you run world-class events, every arrival is a first impression. We make sure it&rsquo;s a remarkable one &mdash; with discreet, chauffeur-driven service your guests will remember.
              </div>
              <table role="presentation" cellpadding="0" cellspacing="0" border="0" align="center" style="margin:32px auto 0 auto;">
                <tr><td align="center" bgcolor="#c9a84c" style="border-radius:6px;">
                  <!--[if mso]><v:roundrect xmlns:v="urn:schemas-microsoft-com:vml" xmlns:w="urn:schemas-microsoft-com:office:word" href="mailto:{SALES_EMAIL}" style="height:50px;v-text-anchor:middle;width:250px;" arcsize="12%" strokecolor="#c9a84c" fillcolor="#c9a84c"><w:anchorlock/><center style="color:#151517;font-family:Arial,sans-serif;font-size:14px;font-weight:bold;letter-spacing:1px;">REQUEST A PROPOSAL</center></v:roundrect><![endif]-->
                  <!--[if !mso]><!-- --><a href="mailto:{SALES_EMAIL}" style="display:inline-block; font-family:Arial,Helvetica,sans-serif; font-size:14px; font-weight:bold; letter-spacing:1px; color:#151517; text-decoration:none; padding:16px 40px; border-radius:6px; background-color:#c9a84c;">REQUEST&nbsp;A&nbsp;PROPOSAL</a><!--<![endif]-->
                </td></tr>
              </table>
            </td>
          </tr>

          <!-- INTRO -->
          <tr>
            <td class="px" style="padding: 44px 48px 10px 48px;">
              <div style="font-family:Georgia,'Times New Roman',serif; font-size:24px; line-height:32px; color:#1e1e20; margin-bottom:16px;">A partner for the moments that matter.</div>
              <div style="font-family:Arial,Helvetica,sans-serif; font-size:15px; line-height:26px; color:#4a4a4e;">
                Pivot Travel Management is a full-service corporate travel partner based in Riyadh. For event managers, exhibition organisers and corporate planners, our <strong>Executive Transportation</strong> division removes the logistics pressure entirely &mdash; from the airport to the venue, and every transfer in between &mdash; with punctual, immaculate, chauffeur-driven service that mirrors the standard of your own brand.
                <br><br>
                One point of contact. One dependable team. Complete peace of mind.
              </div>
            </td>
          </tr>

          <!-- FEATURED SERVICE LABEL -->
          <tr>
            <td class="px" align="center" style="padding: 32px 48px 0 48px;">
              <span style="display:inline-block; font-family:Arial,Helvetica,sans-serif; font-size:10px; letter-spacing:3px; color:#1e1e20; background:#c9a84c; border-radius:20px; padding:6px 16px; text-transform:uppercase;">Our Signature Service</span>
              <div style="font-family:Georgia,'Times New Roman',serif; font-size:27px; color:#1e1e20; margin-top:14px;">Executive Ground Transportation</div>
              <div style="font-family:Arial,Helvetica,sans-serif; font-size:14px; line-height:22px; color:#6a6a6e; max-width:430px; margin:8px auto 0 auto;">Purpose-built for events &mdash; and the core of what we offer event organisers.</div>
            </td>
          </tr>

          <!-- TRANSPORT SERVICES GRID -->
          <tr>
            <td class="px" style="padding: 12px 40px 6px 40px;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">{transport_rows}
              </table>
            </td>
          </tr>

          <!-- CURATED LUXURY strip -->
          <tr>
            <td class="px" style="padding: 6px 52px 6px 52px;">
              <div style="font-family:Arial,Helvetica,sans-serif; font-size:13px; line-height:20px; color:#6a6a6e; text-align:center;"><span style="color:#c9a84c; font-size:16px;">&#10024;</span> &nbsp;<strong style="color:#1e1e20;">Curated Luxury Experiences</strong> &mdash; bespoke journeys tailored to your most important guests.</div>
            </td>
          </tr>

          <!-- FLEET BAND -->
          <tr>
            <td style="padding: 22px 40px 30px 40px;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="#1e1e20" style="background:linear-gradient(180deg,#323234 0%,#1e1e20 100%); border-radius:12px;">
                <tr><td align="center" style="padding:26px 26px 22px 26px;">
                  <div style="font-family:Arial,Helvetica,sans-serif; font-size:11px; letter-spacing:4px; color:#c9a84c; text-transform:uppercase; margin-bottom:12px;">One Fleet, Any Scale</div>
                  <table role="presentation" cellpadding="0" cellspacing="0" border="0" align="center"><tr>
                    <td class="center-m" style="font-family:Georgia,serif; font-size:17px; color:#fff; padding:6px 12px;">Sedans</td><td style="color:#c9a84c;">&bull;</td>
                    <td class="center-m" style="font-family:Georgia,serif; font-size:17px; color:#fff; padding:6px 12px;">SUVs</td><td style="color:#c9a84c;">&bull;</td>
                    <td class="center-m" style="font-family:Georgia,serif; font-size:17px; color:#fff; padding:6px 12px;">Luxury Vans</td><td style="color:#c9a84c;">&bull;</td>
                    <td class="center-m" style="font-family:Georgia,serif; font-size:17px; color:#fff; padding:6px 12px;">Minibuses</td><td style="color:#c9a84c;">&bull;</td>
                    <td class="center-m" style="font-family:Georgia,serif; font-size:17px; color:#fff; padding:6px 12px;">Coaches</td>
                  </tr></table>
                  <div style="font-family:Arial,Helvetica,sans-serif; font-size:13px; line-height:20px; color:#a9a9ad; margin-top:12px; max-width:400px;">Matched precisely to the size and requirements of your event &mdash; from a single executive pickup to a full delegate movement.</div>
                </td></tr>
              </table>
            </td>
          </tr>

          <!-- FULL PORTFOLIO -->
          <tr>
            <td class="px" style="padding: 6px 48px 4px 48px;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr><td style="border-top:1px solid #ece7d8; font-size:0; line-height:0;">&nbsp;</td></tr></table>
            </td>
          </tr>
          <tr>
            <td class="px" align="center" style="padding: 24px 48px 4px 48px;">
              <div style="font-family:Arial,Helvetica,sans-serif; font-size:11px; letter-spacing:4px; color:#c9a84c; text-transform:uppercase; margin-bottom:8px;">Beyond Transportation</div>
              <div style="font-family:Georgia,'Times New Roman',serif; font-size:24px; color:#1e1e20;">The full Pivot travel portfolio</div>
              <div style="font-family:Arial,Helvetica,sans-serif; font-size:14px; line-height:22px; color:#6a6a6e; max-width:440px; margin:8px auto 0 auto;">A single, trusted partner for every corporate travel need &mdash; not only the road.</div>
            </td>
          </tr>
          <tr>
            <td class="px" style="padding: 16px 44px 8px 44px;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">{portfolio_rows}
              </table>
            </td>
          </tr>

          <!-- WHY PIVOT -->
          <tr>
            <td class="px" style="padding: 22px 48px 8px 48px;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
                <tr><td style="padding:8px 0;"><span style="font-family:Georgia,serif; color:#c9a84c; font-size:18px;">&#10003;</span> <span style="font-family:Arial,Helvetica,sans-serif; font-size:14px; color:#3a3a3e; padding-left:6px;"><strong>Reliability</strong> &mdash; punctual, tracked and confirmed at every step.</span></td></tr>
                <tr><td style="padding:8px 0;"><span style="font-family:Georgia,serif; color:#c9a84c; font-size:18px;">&#10003;</span> <span style="font-family:Arial,Helvetica,sans-serif; font-size:14px; color:#3a3a3e; padding-left:6px;"><strong>Attention to detail</strong> &mdash; immaculate vehicles, briefed chauffeurs.</span></td></tr>
                <tr><td style="padding:8px 0;"><span style="font-family:Georgia,serif; color:#c9a84c; font-size:18px;">&#10003;</span> <span style="font-family:Arial,Helvetica,sans-serif; font-size:14px; color:#3a3a3e; padding-left:6px;"><strong>Flexibility</strong> &mdash; scaling with your programme as plans evolve.</span></td></tr>
                <tr><td style="padding:8px 0;"><span style="font-family:Georgia,serif; color:#c9a84c; font-size:18px;">&#10003;</span> <span style="font-family:Arial,Helvetica,sans-serif; font-size:14px; color:#3a3a3e; padding-left:6px;"><strong>Corporate standards</strong> &mdash; a single accountable point of contact.</span></td></tr>
              </table>
            </td>
          </tr>

          <!-- CLOSING CTA -->
          <tr>
            <td align="center" class="px" style="padding: 30px 48px 34px 48px;">
              <div style="font-family:Georgia,'Times New Roman',serif; font-size:23px; line-height:30px; color:#1e1e20; margin-bottom:8px;">Let&rsquo;s make your next event effortless.</div>
              <div style="font-family:Arial,Helvetica,sans-serif; font-size:14px; line-height:23px; color:#6a6a6e; margin-bottom:24px;">Tell us your dates and requirements &mdash; we&rsquo;ll take care of the rest.</div>
              <table role="presentation" cellpadding="0" cellspacing="0" border="0" align="center"><tr>
                <td align="center" bgcolor="#c9a84c" style="border-radius:6px;">
                  <!--[if mso]><v:roundrect xmlns:v="urn:schemas-microsoft-com:vml" xmlns:w="urn:schemas-microsoft-com:office:word" href="mailto:{SENDER_EMAIL}" style="height:50px;v-text-anchor:middle;width:230px;" arcsize="12%" strokecolor="#c9a84c" fillcolor="#c9a84c"><w:anchorlock/><center style="color:#151517;font-family:Arial,sans-serif;font-size:14px;font-weight:bold;letter-spacing:1px;">SPEAK WITH OUR TEAM</center></v:roundrect><![endif]-->
                  <!--[if !mso]><!-- --><a href="mailto:{SENDER_EMAIL}" style="display:inline-block; font-family:Arial,Helvetica,sans-serif; font-size:14px; font-weight:bold; letter-spacing:1px; color:#151517; text-decoration:none; padding:16px 36px; border-radius:6px; background-color:#c9a84c;">SPEAK&nbsp;WITH&nbsp;OUR&nbsp;TEAM</a><!--<![endif]-->
                </td>
              </tr></table>
            </td>
          </tr>

          <!-- SIGNATURE -->
          <tr>
            <td class="px" style="padding: 4px 48px 30px 48px;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="border:1px solid #ece7d8; border-radius:12px;">
                <tr>
                  <td valign="top" style="padding:20px 22px;">
                    <div style="font-family:Georgia,'Times New Roman',serif; font-size:19px; color:#1e1e20;">{SENDER_NAME}</div>
                    <div style="font-family:Arial,Helvetica,sans-serif; font-size:12px; color:#c9a84c; letter-spacing:1px; text-transform:uppercase; margin-top:3px;">{SENDER_TITLE}</div>
                    <div style="font-family:Arial,Helvetica,sans-serif; font-size:12px; color:#8a8a8e; margin-top:2px;">{SENDER_DEPT} &middot; Pivot Travel Management</div>
                    <table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin-top:14px;">
                      <tr><td style="font-family:Arial,Helvetica,sans-serif; font-size:13px; color:#3a3a3e; padding:3px 0;">&#128241;&nbsp; <a href="tel:{SENDER_MOBILE.replace(' ','')}" style="color:#3a3a3e; text-decoration:none;">{SENDER_MOBILE}</a> &nbsp;<span style="color:#b8b8bc;">(mobile)</span></td></tr>
                      <tr><td style="font-family:Arial,Helvetica,sans-serif; font-size:13px; color:#3a3a3e; padding:3px 0;">&#9742;&nbsp; <a href="tel:{SENDER_TEL.replace(' ','')}" style="color:#3a3a3e; text-decoration:none;">{SENDER_TEL}</a>, Ext. {SENDER_EXT}</td></tr>
                      <tr><td style="font-family:Arial,Helvetica,sans-serif; font-size:13px; color:#3a3a3e; padding:3px 0;">&#9993;&nbsp; <a href="mailto:{SENDER_EMAIL}" style="color:#3a3a3e; text-decoration:none;">{SENDER_EMAIL}</a></td></tr>
                    </table>
                    <div style="margin-top:14px;">
                      <a href="{WHATSAPP}" style="font-family:Arial,Helvetica,sans-serif; font-size:11px; letter-spacing:1px; color:#1e1e20; text-decoration:none; background:#c9a84c; border-radius:20px; padding:8px 18px; display:inline-block;">CHAT ON WHATSAPP</a>
                    </div>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- FOOTER -->
          <tr>
            <td bgcolor="#0e0e0f" style="background:linear-gradient(180deg,#1e1e20 0%,#0e0e0f 100%); padding: 34px 40px 30px 40px;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr><td align="center">
                <div style="font-family:Georgia,'Times New Roman',serif; font-size:16px; letter-spacing:2px; color:#ffffff; margin-bottom:6px;">PIVOT&nbsp;TRAVEL&nbsp;MANAGEMENT</div>
                <div style="height:2px; width:48px; background:#c9a84c; margin:8px auto 16px auto; line-height:2px; font-size:0;">&nbsp;</div>
                <div style="font-family:Arial,Helvetica,sans-serif; font-size:12px; line-height:20px; color:#9a9a9e;">
                  Suite 20, 2nd Floor, Mobco Building, 2762 Ibn Al Anbari Street,<br>
                  Al Amal District, Riyadh, Kingdom of Saudi Arabia<br>
                  CR No. 7043148696
                </div>
                <div style="margin:18px 0 6px 0;">
                  <a href="tel:{SENDER_TEL.replace(' ','')}" style="font-family:Arial,Helvetica,sans-serif; font-size:12px; color:#c9a84c; text-decoration:none; padding:0 8px;">{SENDER_TEL}</a>
                  <span style="color:#3a3a3e;">|</span>
                  <a href="mailto:{SALES_EMAIL}" style="font-family:Arial,Helvetica,sans-serif; font-size:12px; color:#c9a84c; text-decoration:none; padding:0 8px;">{SALES_EMAIL}</a>
                  <span style="color:#3a3a3e;">|</span>
                  <a href="{WEBSITE}" style="font-family:Arial,Helvetica,sans-serif; font-size:12px; color:#c9a84c; text-decoration:none; padding:0 8px;">www.pivot-travels.com</a>
                </div>
                <div style="font-family:Arial,Helvetica,sans-serif; font-size:10px; color:#5a5a5e; margin-top:22px;">&copy; 2026 Pivot Travel Management. All rights reserved.</div>
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
