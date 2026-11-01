#!/usr/bin/env python3
"""Generates the watch face drawables and res/raw/watchface.xml.

The Persona-5-Calendar art is drawn on a shared 835x653 canvas, so layers only
line up when they share a scale and origin. This script scales every layer
together, crops it to its visible pixels and records where the crop belongs.

    pip install pillow
    python3 tools/generate_watchface.py [path/to/Persona-5-Calendar]
"""
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "watchface/src/main/res"
OUT = RES / "drawable"
SOURCE = ROOT / "tools/source"
FONT = RES / "font/markin_lt_ultrabold.ttf"
CALENDAR = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT.parent / "Persona-5-Calendar"
ASSETS = CALENDAR / "Assets"

FACE = 450
RENDER = 2  # Bitmaps are stored at 2x so they stay sharp on larger watches.
SAFE_RADIUS = 221
BACKGROUND_SIZE = 480
NIGHT_BLACK_POINT = 24
XIAOMI_STEPS = ("com.xiaomi.miwear.watchface/"
                "com.xiaomi.miwear.watchface.complication.health.vigor.StepComplicationDataSource")

CANVAS = (835, 653)
CALENDAR_SCALE, CALENDAR_X, CALENDAR_Y = 0.36, 56, 34
TOD_SCALE, TOD_X, TOD_Y = 0.28, 274, 33

# Version 1 of the art is black-on-white stickers for the light background.
NIGHT, DAY = 0, 1
WEEKDAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
WEATHER_ICONS = ["01", "02", "03", "04", "09", "10", "11", "13", "50"]
# [WEATHER.CONDITION] -> OpenWeatherMap icon. 0 (unknown) uses the blank tag.
CONDITIONS = {1: "01", 2: "04", 3: "50", 4: "10", 5: "13", 6: "09", 7: "13", 8: "01", 9: "11",
              10: "13", 11: "13", 12: "09", 13: "50", 14: "02", 15: "03"}
# Time of day art, using the hour bands from the Rainmeter skin.
TOD_HOURS = [(1, "[HOUR_0_23] &lt; 1"), (2, "[HOUR_0_23] &lt; 7"), (3, "[HOUR_0_23] &lt; 11"),
             (4, "[HOUR_0_23] &lt; 14"), (5, "[HOUR_0_23] &lt; 19"), (6, "[HOUR_0_23] &lt; 21")]

RED = (230, 0, 18, 255)
WHITE = (255, 255, 255, 255)
BLACK = (10, 10, 10, 255)
CYAN, MAGENTA, YELLOW = "#ff00e5ff", "#ffff3dc8", "#ffffe600"

# Weather arrives in the unit set on the watch, where 2 means Fahrenheit.
CELSIUS = ("[WEATHER.TEMPERATURE_UNIT] == 2 ? round(([WEATHER.TEMPERATURE] - 32.0) * 5.0 / 9.0) "
           ": [WEATHER.TEMPERATURE]")

DIGIT_SIZE = 94
GLYPHS = "0123456789:"
CLOCK_ANGLE = -4
CLOCK_Y, CLOCK_SPLIT = 218, 248  # Hours end at the split, minutes start there.
STATUS_X, STATUS_Y, STATUS_W, STATUS_H = 56, 324, 338, 50

resource_count = 0


def save(image, name):
    global resource_count
    resource_count += 1
    image.save(OUT / f"{name}.png", optimize=True)


def check_on_screen(name, x, y, image):
    """Rejects art that the round display would clip."""
    alpha = image.getchannel("A").point(lambda v: 255 if v > 20 else 0)
    mask = Image.new("L", image.size, 255)
    center = ((FACE / 2 - x) * RENDER, (FACE / 2 - y) * RENDER)
    r = SAFE_RADIUS * RENDER
    ImageDraw.Draw(mask).ellipse((center[0] - r, center[1] - r, center[0] + r, center[1] + r), fill=0)
    if ImageChops.multiply(alpha, mask).getbbox():
        raise SystemExit(f"{name} leaves the round display")


def place(source, scale, origin_x, origin_y):
    """Scales a canvas layer and crops it. Returns the crop and its face position."""
    canvas = Image.new("RGBA", CANVAS)
    canvas.paste(source.crop((0, 0, *CANVAS)))
    size = (round(CANVAS[0] * scale * RENDER), round(CANVAS[1] * scale * RENDER))
    scaled = canvas.resize(size, Image.LANCZOS)
    left, top, right, bottom = scaled.getbbox()
    # Whole face pixels keep the three layers of each sticker aligned.
    left -= left % RENDER
    top -= top % RENDER
    right += -right % RENDER
    bottom += -bottom % RENDER
    return (scaled.crop((left, top, right, bottom)), origin_x + left // RENDER,
            origin_y + top // RENDER, (right - left) // RENDER, (bottom - top) // RENDER)


def part(name, x, y, w, h):
    return f'<PartImage x="{x}" y="{y}" width="{w}" height="{h}"><Image resource="{name}" /></PartImage>'


def art(source, name, scale=CALENDAR_SCALE, x=CALENDAR_X, y=CALENDAR_Y):
    crop, left, top, w, h = place(Image.open(source).convert("RGBA"), scale, x, y)
    check_on_screen(name, left, top, crop)
    save(crop, name)
    return part(name, left, top, w, h)


def condition(cases, default=None, indent=16):
    """cases is a list of (expression, content) in priority order."""
    pad = " " * indent
    lines = [f"{pad}<Condition>", f"{pad}    <Expressions>"]
    lines += [f'{pad}        <Expression name="c{i}">{e}</Expression>' for i, (e, _) in enumerate(cases)]
    lines.append(f"{pad}    </Expressions>")
    lines += [f'{pad}    <Compare expression="c{i}">{c}</Compare>' for i, (_, c) in enumerate(cases)]
    if default:
        lines.append(f"{pad}    <Default>{default}</Default>")
    lines.append(f"{pad}</Condition>")
    return "\n".join(lines)


def calendar_layers(v):
    """Returns the calendar in the skin's order: white shapes, weather, black shapes, numbers."""
    tag = f"p5_v{v}"
    layers = []

    def day(suffix, layer):
        return condition([(f"[DAY] == {d}", art(ASSETS / f"Day/{v}/{d}{suffix}.png", f"{tag}_day_{d}{layer}"))
                          for d in range(1, 32)])

    def month(suffix, layer):
        # The month moves left to make room for a two-digit day.
        cases = []
        for m in range(1, 13):
            cases.append((f"[MONTH] == {m} &amp;&amp; [DAY] &lt; 10",
                          art(ASSETS / f"Month/{v}/{m}{suffix}.png", f"{tag}_month_{m}{layer}")))
            cases.append((f"[MONTH] == {m}",
                          art(ASSETS / f"Month/{v}/{m * 100}{suffix}.png", f"{tag}_month_{m}_wide{layer}")))
        return condition(cases)

    def week(suffix, layer):
        return condition([(f"[DAY_OF_WEEK] == {i + 1}",
                           art(ASSETS / f"Week/{v}/{d}{suffix}.png", f"{tag}_week_{d.lower()}{layer}"))
                          for i, d in enumerate(WEEKDAYS)])

    layers += [day("Bottom", "_bottom"), month("Bottom", "_bottom"), week("Bottom", "_bottom")]
    layers.append(weather(v))
    layers += [day("", ""), month("", ""), week("", "")]
    layers += [day("Top", "_top"), month("Top", "_top"), week("Top", "_top")]
    return layers


def blank_tag(v, folder, name):
    """Draws the weather tag without an icon, shown while no forecast is available."""
    source = Image.open(ASSETS / f"Weather/{folder}/{v}/01d.png").convert("RGBA")
    crop, x, y, w, h = place(source, CALENDAR_SCALE, CALENDAR_X, CALENDAR_Y)
    paper, ink = (BLACK, WHITE) if v == DAY else (WHITE, BLACK)
    blank = Image.new("RGBA", crop.size, paper)
    blank.putalpha(crop.getchannel("A"))
    font = ImageFont.truetype(str(FONT), 46 * RENDER)
    ImageDraw.Draw(blank).text((crop.width / 2, crop.height / 2), "?", font=font, fill=ink, anchor="mm")
    check_on_screen(name, x, y, blank)
    save(blank, name)
    return part(name, x, y, w, h)


def weather(v):
    tag = f"p5_v{v}"
    images = {}

    def icons(folder, layout):
        cases = []
        for condition_id, icon in CONDITIONS.items():
            for suffix, sky in (("d", "[WEATHER.IS_DAY]"), ("n", "![WEATHER.IS_DAY]")):
                name = f"{tag}_weather_{icon}{suffix}{layout}"
                if name not in images:
                    images[name] = art(ASSETS / f"Weather/{folder}/{v}/{icon}{suffix}.png", name)
                cases.append((f"[WEATHER.IS_AVAILABLE] &amp;&amp; [WEATHER.CONDITION] == {condition_id} "
                              f"&amp;&amp; {sky}", images[name]))
        return condition(cases, blank_tag(v, folder, f"{tag}_weather_blank{layout}"), 24)

    # The tag sits further right when the day has two digits.
    return condition([("[DAY] &lt; 10", f"\n{icons('icons3', '_narrow')}\n")],
                     f"\n{icons('icons0', '_wide')}\n")


def time_of_day(v):
    images = {t: art(ASSETS / f"ToD/{v}/{t}.png", f"p5_v{v}_tod_{t}", TOD_SCALE, TOD_X, TOD_Y)
              for t in range(1, 7)}
    return condition([(e, images[t]) for t, e in TOD_HOURS], images[1])


def background(name, source, black_point=0):
    """Takes a square crop of the portrait art, keeping the skyline below the middle.

    Values at or below black_point become pure black, which turns OLED pixels off.
    """
    image = Image.open(SOURCE / source).convert("RGB")
    side = image.width
    top = round(image.height * 0.22)
    image = image.crop((0, top, side, top + side)).resize((BACKGROUND_SIZE,) * 2, Image.LANCZOS)
    if black_point:
        scale = 255 / (255 - black_point)
        # PNG, because JPEG noise would light up the pure black pixels again.
        image.point(lambda v: max(0, round((v - black_point) * scale))).save(OUT / f"{name}.png", optimize=True)
    else:
        image.save(OUT / f"{name}.jpg", quality=90, optimize=True)
    return f'<PartImage x="0" y="0" width="{FACE}" height="{FACE}"><Image resource="{name}" /></PartImage>'


def glyph_font(name, fill, outline, shadow, stroke, shadow_offset, halo):
    """Renders digits as stickers and returns their BitmapFont definition."""
    font = ImageFont.truetype(str(FONT), DIGIT_SIZE * RENDER)
    pad = (stroke + halo) * RENDER
    tail = shadow_offset * RENDER
    top = min(font.getbbox(c, anchor="ls")[1] for c in GLYPHS)
    bottom = max(font.getbbox(c, anchor="ls")[3] for c in GLYPHS)
    height = bottom - top + pad * 2 + tail
    height += -height % RENDER
    chars = []
    for glyph in GLYPHS:
        box = font.getbbox(glyph, anchor="ls")
        width = box[2] - box[0] + pad * 2 + tail
        width += -width % RENDER
        origin = (pad - box[0], pad - top)
        image = Image.new("RGBA", (width, height))
        draw = ImageDraw.Draw(image)

        def text(offset, color, stroke_width):
            draw.text((origin[0] + offset, origin[1] + offset), glyph, font=font, fill=color, anchor="ls",
                      stroke_width=stroke_width * RENDER, stroke_fill=color)

        if halo:
            text(shadow_offset * RENDER, WHITE, stroke + halo)
            text(0, WHITE, stroke + halo)
        if shadow:
            text(shadow_offset * RENDER, shadow, stroke)
        text(0, outline, stroke)
        draw.text(origin, glyph, font=font, fill=fill, anchor="ls")
        resource = f"{name}_{'colon' if glyph == ':' else glyph}"
        save(image, resource)
        chars.append(f'            <Character name="{glyph}" resource="{resource}" '
                     f'width="{width // RENDER}" height="{height // RENDER}" />')
    return (f'        <BitmapFont name="{name}">\n' + "\n".join(chars) + "\n        </BitmapFont>",
            height // RENDER)


def clock(hours_font, minutes_font, height, y=CLOCK_Y):
    width = 200

    def text(font, align, template, x):
        return (f'<PartText x="{x}" y="{y}" width="{width}" height="{height}"><Text align="{align}">'
                f'<BitmapFont family="{font}" size="{height}"><Template>{template}</Template></BitmapFont>'
                f'</Text></PartText>')

    hours = text(hours_font, "END", '%s:<Parameter expression="[HOUR_0_23_Z]" />', CLOCK_SPLIT - width)
    minutes = text(minutes_font, "START", '%s<Parameter expression="[MINUTE_Z]" />', CLOCK_SPLIT)
    return f"{hours}\n            {minutes}"


def status_bar():
    """Draws the slanted black bar and its battery and step icons."""
    w, h = STATUS_W * RENDER, STATUS_H * RENDER
    bar = Image.new("RGBA", (w, h))
    draw = ImageDraw.Draw(bar)
    slant = 16 * RENDER
    white_h = 6 * RENDER
    draw.polygon([(slant, 0), (w, 0), (w - slant, h - white_h), (0, h - white_h)], fill=BLACK)
    draw.polygon([(8 * RENDER, h - white_h + 2), (w - slant - 2 * RENDER, h - white_h + 2),
                  (w - slant - 8 * RENDER, h), (2 * RENDER, h)], fill=WHITE)

    def scaled(*values):
        return [v * RENDER for v in values]

    cyan, magenta = (0, 229, 255, 255), (255, 61, 200, 255)
    draw.rounded_rectangle(scaled(26, 12, 54, 30), radius=3 * RENDER, outline=cyan, width=3 * RENDER)
    draw.rectangle(scaled(55, 17, 58, 25), fill=cyan)
    draw.rectangle(scaled(31, 17, 45, 25), fill=cyan)
    draw.ellipse(scaled(138, 11, 148, 25), fill=magenta)
    draw.ellipse(scaled(150, 15, 160, 29), fill=magenta)
    draw.ellipse(scaled(139, 27, 146, 33), fill=magenta)
    draw.ellipse(scaled(151, 31, 158, 37), fill=magenta)
    save(bar, "p5_status_bar")
    return part("p5_status_bar", 0, 0, STATUS_W, STATUS_H)


def status_text(x, w, color, template, y=6):
    return (f'<PartText x="{x}" y="{y}" width="{w}" height="32"><Text align="START">'
            f'<Font family="markin_lt_ultrabold" size="23" color="{color}"><Template>{template}</Template></Font>'
            f'</Text></PartText>')


def steps_slot(hide_in_ambient):
    # [STEP_COUNT] goes stale on Xiaomi watches, so prefer their own step source.
    # The runtime only finds slots directly under Scene, so this one repeats the
    # status bar's position and tilt instead of sitting inside its group.
    text = status_text(0, 84, MAGENTA, '%s<Parameter expression="[COMPLICATION.TEXT]" />', 0)
    return f"""<ComplicationSlot x="221" y="328" width="84" height="32" angle="-3" slotId="0" displayName="steps_complication" supportedTypes="SHORT_TEXT">
            {hide_in_ambient}
            <DefaultProviderPolicy defaultSystemProvider="STEP_COUNT" defaultSystemProviderType="SHORT_TEXT" primaryProvider="{XIAOMI_STEPS}" primaryProviderType="SHORT_TEXT" />
            <BoundingBox x="0" y="0" width="84" height="32" />
            <Complication type="SHORT_TEXT">{text}</Complication>
        </ComplicationSlot>"""


def main():
    if not ASSETS.is_dir():
        raise SystemExit(f"Calendar assets not found at {ASSETS}")
    for path in OUT.glob("p5_*"):
        path.unlink()

    day_background = background("p5_bg_day", "persona_day.jpg")
    night_background = background("p5_bg_night", "persona_night.jpg", NIGHT_BLACK_POINT)
    hours_font, digit_height = glyph_font("p5_clock_hours", WHITE, BLACK, RED, 6, 5, 3)
    minutes_font, _ = glyph_font("p5_clock_minutes", RED, BLACK, WHITE, 6, 5, 3)
    ambient_font, ambient_height = glyph_font("p5_clock_ambient", BLACK, WHITE, None, 3, 0, 0)
    ambient_y = CLOCK_Y + (digit_height - ambient_height) // 2

    day_layers = "\n".join(calendar_layers(DAY) + [time_of_day(DAY)])
    night_layers = "\n".join(calendar_layers(NIGHT) + [time_of_day(NIGHT)])
    full = f'x="0" y="0" width="{FACE}" height="{FACE}"'
    hide_in_ambient = '<Variant mode="AMBIENT" target="alpha" value="0" />'
    temperature = condition(
        [("[WEATHER.IS_AVAILABLE]", status_text(253, 68, YELLOW, f'%d°<Parameter expression="{CELSIUS}" />'))],
        status_text(253, 68, YELLOW, "--°"), 16)

    xml = f"""<?xml version="1.0" encoding="utf-8"?>
<!-- Generated by tools/generate_watchface.py. Edit that script, not this file. -->
<WatchFace width="{FACE}" height="{FACE}">
    <Metadata key="CLOCK_TYPE" value="DIGITAL" />
    <BitmapFonts>
{hours_font}
{minutes_font}
{ambient_font}
    </BitmapFonts>
    <Scene backgroundColor="#ff000000">
        <Group name="interactive" {full} alpha="255">
            {hide_in_ambient}
            <Condition>
                <Expressions>
                    <Expression name="daytime">[HOUR_0_23] &gt;= 6 &amp;&amp; [HOUR_0_23] &lt; 18</Expression>
                </Expressions>
                <Compare expression="daytime">
                    <Group name="day_theme" {full}>
                        {day_background}
{day_layers}
                    </Group>
                </Compare>
                <Default>
                    <Group name="night_theme" {full}>
                        {night_background}
{night_layers}
                    </Group>
                </Default>
            </Condition>
            <Group name="status" x="{STATUS_X}" y="{STATUS_Y}" width="{STATUS_W}" height="{STATUS_H}" angle="-3">
                {status_bar()}
                {status_text(62, 72, CYAN, '%s%%<Parameter expression="[BATTERY_PERCENT]" />')}
{temperature}
            </Group>
            <Group name="clock" {full} angle="{CLOCK_ANGLE}">
            {clock("p5_clock_hours", "p5_clock_minutes", digit_height)}
            </Group>
        </Group>
        {steps_slot(hide_in_ambient)}
        <Group name="ambient" {full} alpha="0">
            <Variant mode="AMBIENT" target="alpha" value="255" />
            <Group name="ambient_clock" {full} angle="{CLOCK_ANGLE}">
            {clock("p5_clock_ambient", "p5_clock_ambient", ambient_height, ambient_y)}
            </Group>
            <PartText x="75" y="{CLOCK_Y + 112}" width="300" height="40">
                <Text align="CENTER">
                    <Font family="markin_lt_ultrabold" size="28" color="#ffffffff">
                        <Template>%s/%s %s<Parameter expression="[MONTH]" /><Parameter expression="[DAY]" /><Parameter expression="[DAY_OF_WEEK_S]" /></Template>
                    </Font>
                </Text>
            </PartText>
        </Group>
    </Scene>
</WatchFace>
"""
    (RES / "raw/watchface.xml").write_text(xml, encoding="utf-8")
    print(f"{resource_count} images, {len(xml.splitlines())} xml lines")


if __name__ == "__main__":
    main()
