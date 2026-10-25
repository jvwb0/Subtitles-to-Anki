# services/anki_note_template.py
"""
Visual design (HTML/CSS) for the "Subtitles to Anki" note type — kept
separate from anki_service.py so that "talk to AnkiConnect" (API calls) and
"what a card looks like" (template design) are two distinct concerns.
"""


class AnkiNoteTemplate:
    MODEL_NAME = "Subtitles to Anki"
    FIELDS = ["Word", "Meaning", "Grammar", "Example", "Example Translation", "Register"]

    CSS = """\
.card{
  font-family: Calibri, Arial, sans-serif;
  font-size: 22px;
  line-height: 1.45;
  color:#111;
  background:#f4f4f4;
  padding:24px;
  text-align:center;
}
.pattern{
  font-size:34px;
  font-weight:900;
  letter-spacing:0.3px;
  margin:6px 0 16px 0;
}
.meaning{
  font-size:20px;
  opacity:.9;
  margin:0 0 10px 0;
}
.meta{
  font-size:16px;
  opacity:.75;
  margin:0 0 14px 0;
}
.box{
  text-align:left;
  max-width:760px;
  margin:14px auto 0 auto;
  padding:14px 16px;
  border-radius:16px;
  background:#fff;
  border:1px solid rgba(0,0,0,.10);
}
.label{
  font-size:12px;
  font-weight:900;
  opacity:.6;
  letter-spacing:1px;
  margin-bottom:6px;
}
.example-src{
  font-size:20px;
  font-style:italic;
}
.example-tgt{
  font-size:18px;
  opacity:.88;
}
.tag{
  margin-top:14px;
  display:inline-block;
  font-size:12px;
  font-weight:800;
  padding:6px 10px;
  border-radius:999px;
  border:1px solid rgba(0,0,0,.14);
  background:#fff;
  opacity:.8;
}
a.hint{
  text-decoration:none;
  font-weight:900;
  padding:6px 10px;
  border-radius:999px;
  border:1px solid rgba(0,0,0,.14);
  background:#f7f7f7;
  color:#111;
}
"""

    FRONT = """\
<div class="pattern">{{Word}}</div>

{{#Example}}
<br>
  <div class="box">
    <div class="label">EXAMPLE</div>
    <div class="example-src">{{Example}}</div>
  </div>
{{/Example}}
"""

    BACK = """\
<div class="pattern">{{Word}}</div>

<div class="meaning">{{Meaning}}</div>

{{#Grammar}}
  <div class="meta">{{Grammar}}</div>
{{/Grammar}}

{{#Example}}
  <div class="box">
    <div class="label">EXAMPLE</div>
    <div class="example-src">{{Example}}</div>
  </div>
{{/Example}}

{{#Example Translation}}
  <div class="box">
    <div class="label">TRANSLATION</div>
    <div class="example-tgt">{{hint:Example Translation}}</div>
  </div>
{{/Example Translation}}

{{#Register}}
  <div class="tag">{{Register}}</div>
{{/Register}}
"""
