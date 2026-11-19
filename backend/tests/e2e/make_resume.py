import sys
from reportlab.pdfgen import canvas
c = canvas.Canvas("sample_resume.pdf")
c.setFont("Helvetica-Bold", 16); c.drawString(72, 780, "Asha Rao")
c.setFont("Helvetica", 10); c.drawString(72, 762, "Bengaluru | asha@example.com | +91 98765 43210")
c.drawString(72, 744, "LinkedIn"); c.linkURL("https://www.linkedin.com/in/asha-rao-123/", (72, 740, 112, 754))
c.drawString(130, 744, "GitHub"); c.linkURL("https://github.com/asharao", (130, 740, 165, 754))
c.drawString(185, 744, "Portfolio"); c.linkURL("https://asha.dev", (185, 740, 230, 754))
c.drawString(72, 720, "Project: ShopFast"); c.linkURL("https://github.com/asharao/shopfast", (72, 716, 160, 730))
c.drawString(72, 690, "Senior engineer with 6 years of experience building backend services in Python and Go at scale.")
c.save()

import docx
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.opc.constants import RELATIONSHIP_TYPE as RT
d = docx.Document()
def link(par, url, text):
    rid = par.part.relate_to(url, RT.HYPERLINK, is_external=True)
    h = OxmlElement("w:hyperlink"); h.set(qn("r:id"), rid)
    r = OxmlElement("w:r"); t = OxmlElement("w:t"); t.text = text; r.append(t); h.append(r); par._p.append(h)
hp = d.sections[0].header.paragraphs[0]; hp.add_run("Asha Rao  "); link(hp, "https://www.linkedin.com/in/asha-rao-123", "LinkedIn")
p = d.add_paragraph("Contact: "); link(p, "mailto:asha@example.com", "Email me"); p.add_run("  "); link(p, "https://github.com/asharao", "GitHub")
d.add_paragraph("Senior engineer with 6 years of experience building backend services in Python and Go at scale.")
d.save("sample_resume.docx")
