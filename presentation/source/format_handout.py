from pathlib import Path
import re
from docx import Document
from docx.enum.text import WD_LINE_SPACING, WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor


def set_font(style, size, bold=False, color=None):
    style.font.name = 'Microsoft YaHei'
    style.font.size = Pt(size)
    style.font.bold = bold
    if color:
        style.font.color.rgb = RGBColor(*color)
    rpr = style.element.get_or_add_rPr()
    rfonts = rpr.rFonts
    if rfonts is None:
        rfonts = OxmlElement('w:rFonts')
        rpr.insert(0, rfonts)
    rfonts.set(qn('w:eastAsia'), 'Microsoft YaHei')
    rfonts.set(qn('w:ascii'), 'Microsoft YaHei')
    rfonts.set(qn('w:hAnsi'), 'Microsoft YaHei')


root = Path(__file__).parent
source = root / '烟花爆竹管制-讲稿与答辩问答.docx'
dest = root.parent / '烟花爆竹管制-讲稿与答辩问答.docx'
doc = Document(source)
section = doc.sections[0]
section.page_width = Cm(21)
section.page_height = Cm(29.7)
section.top_margin = Cm(2.05)
section.bottom_margin = Cm(1.85)
section.left_margin = Cm(2.25)
section.right_margin = Cm(2.25)

styles = {style.name: style for style in doc.styles}
for name in ('Normal', 'First Paragraph'):
    set_font(styles[name], 10.7)
    styles[name].paragraph_format.line_spacing = 1.25
    styles[name].paragraph_format.space_after = Pt(6)
set_font(styles['Body Text'], 10.3)
styles['Body Text'].paragraph_format.line_spacing = 1.2
styles['Body Text'].paragraph_format.space_after = Pt(4)
set_font(styles['Heading 1'], 18.5, True, (58, 35, 72))
set_font(styles['Heading 2'], 15.5, True, (77, 44, 100))
set_font(styles['Heading 3'], 12.7, True, (77, 44, 100))
for name, before, after in [('Heading 1', 0, 13), ('Heading 2', 13, 8), ('Heading 3', 11, 5)]:
    st = styles[name]
    st.paragraph_format.space_before = Pt(before)
    st.paragraph_format.space_after = Pt(after)
    st.paragraph_format.keep_with_next = True

for paragraph in doc.paragraphs:
    if re.match(r'^\d+\.\s', paragraph.text):
        paragraph.paragraph_format.keep_with_next = True
        paragraph.paragraph_format.space_before = Pt(4)
        paragraph.paragraph_format.space_after = Pt(2)
    if paragraph.text.startswith('可能的答辩问题与建议回答'):
        paragraph.paragraph_format.page_break_before = True
    if paragraph.text.startswith('配套材料：'):
        for run in paragraph.runs:
            run.font.color.rgb = RGBColor(102, 92, 111)
            run.font.size = Pt(9.5)
    if paragraph.text.startswith('答辩前核对清单'):
        paragraph.paragraph_format.page_break_before = True
    for run in paragraph.runs:
        run.font.name = 'Microsoft YaHei'
        rpr = run._element.get_or_add_rPr()
        rfonts = rpr.rFonts
        if rfonts is None:
            rfonts = OxmlElement('w:rFonts')
            rpr.insert(0, rfonts)
        rfonts.set(qn('w:eastAsia'), 'Microsoft YaHei')

footer = section.footer.paragraphs[0]
footer.alignment = WD_ALIGN_PARAGRAPH.RIGHT
run = footer.add_run('烟花爆竹管制中的工具选择  ·  ')
run.font.size = Pt(8.5)
run.font.color.rgb = RGBColor(120, 111, 129)
field = OxmlElement('w:fldSimple')
field.set(qn('w:instr'), 'PAGE')
footer._p.append(field)

doc.save(dest)
print(dest)
