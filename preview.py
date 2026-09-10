import gi
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Pango
import markdown as md_lib


def _theme_hex(style_context, name: str, fallback: str) -> str:
    found, c = style_context.lookup_color(name)
    if not found:
        return fallback
    return "#{:02x}{:02x}{:02x}".format(int(c.red * 255), int(c.green * 255), int(c.blue * 255))


def _theme_font(style_context) -> tuple[str, float]:
    """The GTK theme's UI font, as a CSS family and a size in px.

    The preview is a separate HTML document, so it doesn't inherit the panel's
    GTK style — the font has to be carried across the same way the colors are,
    or the rendered note ends up in a different typeface than the buffer it was
    typed in. Pango sizes are in points against the screen's resolution, while
    WebKit would resolve a `pt` in CSS against a fixed 96dpi, which is why this
    converts rather than passing the points through: at any other DPI (a HiDPI
    screen, GNOME's text-scaling factor) the two would drift apart.
    """
    try:
        desc = style_context.get_property("font", style_context.get_state())
        family = desc.get_family() or "sans-serif"
        size = desc.get_size() / Pango.SCALE
        if desc.get_size_is_absolute():
            return family, round(size, 1)
        dpi = Gdk.Screen.get_default().get_resolution()
        if dpi <= 0:                      # unset — X reports -1, not an error
            dpi = 96.0
        return family, round(size * dpi / 72.0, 1)
    except Exception:
        return "sans-serif", 14.7         # Ubuntu's default, 11pt at 96dpi


def build_preview_html(content: str, style_context) -> str:
    bg      = _theme_hex(style_context, "theme_base_color",        "#272727")
    fg      = _theme_hex(style_context, "theme_text_color",        "#ffffff")
    accent  = _theme_hex(style_context, "theme_selected_bg_color", "#da3450")
    border  = _theme_hex(style_context, "borders",                 "#181818")
    code_bg = _theme_hex(style_context, "theme_bg_color",          "#2c2c2c")

    font_family, font_px = _theme_font(style_context)

    body = md_lib.markdown(
        content,
        extensions=["fenced_code", "tables", "nl2br", "sane_lists"],
    )

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
    background: {bg};
    color: {fg};
    font-family: "{font_family}", sans-serif;
    font-size: {font_px}px;
    line-height: 1.6;
    padding: 14px;
    word-wrap: break-word;
}}
h1, h2, h3, h4 {{
    color: {accent};
    margin: 1em 0 .4em;
    line-height: 1.2;
}}
h1 {{ font-size: 1.5em; border-bottom: 1px solid {border}; padding-bottom: .3em; }}
h2 {{ font-size: 1.25em; }}
h3 {{ font-size: 1.05em; }}
p {{ margin: .5em 0; }}
a {{ color: {accent}; }}
code {{
    background: {code_bg};
    border: 1px solid {border};
    border-radius: 4px;
    padding: 1px 5px;
    font-family: monospace;
    font-size: 0.85em;
}}
pre {{
    background: {code_bg};
    border: 1px solid {border};
    border-radius: 6px;
    padding: 10px 12px;
    overflow-x: auto;
    margin: .6em 0;
}}
pre code {{
    background: transparent;
    border: none;
    padding: 0;
    font-size: 0.85em;
}}
blockquote {{
    border-left: 3px solid {accent};
    margin: .5em 0;
    padding: .2em .8em;
    opacity: .8;
}}
ul, ol {{ padding-left: 1.4em; margin: .4em 0; }}
li {{ margin: .15em 0; }}
table {{ border-collapse: collapse; width: 100%; margin: .6em 0; }}
th, td {{ border: 1px solid {border}; padding: 5px 10px; text-align: left; }}
th {{ background: {code_bg}; color: {accent}; }}
hr {{ border: none; border-top: 1px solid {border}; margin: 1em 0; }}
</style></head><body>{body}</body></html>"""
