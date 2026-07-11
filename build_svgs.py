"""Generate dark_mode.svg and light_mode.svg with embedded ascii art."""
import base64
import html
import re
from datetime import datetime
from pathlib import Path

from dateutil import relativedelta

ROOT = Path(__file__).parent
RX = '955'
LINE_WIDTH = 57

diff = relativedelta.relativedelta(datetime.today(), datetime(1997, 4, 29))
plural = lambda n, w: w + ('s' if n != 1 else '')
MOHSEN_UPTIME = (
    f"{diff.years} {plural(diff.years, 'year')}, "
    f"{diff.months} {plural(diff.months, 'month')}, "
    f"{diff.days} {plural(diff.days, 'day')}"
)

REPO_COUNT, STAR_COUNT, FOLLOWER_COUNT = 34, 26, 13


def esc(value):
    return html.escape(str(value), quote=False)


def dots(label_plain, value):
    prefix_len = len(f'. {label_plain}:')
    gap = max(1, LINE_WIDTH - prefix_len - len(str(value)) - 1)
    return ' ' + ('.' * gap) + ' '


def row(y, label_plain, key_html, value, element_id=None):
    dot_string = dots(label_plain, value)
    dots_id = f' id="{element_id}_dots"' if element_id else ''
    value_id = f' id="{element_id}"' if element_id else ''
    return (
        f'<tspan x="390" y="{y}" class="cc">. </tspan>{key_html}:'
        f'<tspan class="cc"{dots_id}>{dot_string}</tspan>'
        f'<tspan class="value"{value_id} text-anchor="end" x="{RX}" y="{y}">{esc(value)}</tspan>\n'
    )


def build_text(text_fill):
    sep = ' -' + '\u2014' * 37 + '-\u2014-\n'
    contact_sep = '- Contact</tspan> -' + '\u2014' * 37 + '-\u2014-\n'
    stats_sep = '- GitHub Stats</tspan> -' + '\u2014' * 33 + '-\u2014-\n'

    loc_value = '0 ( 0++, 0-- )'
    loc_dots = dots('Lines of Code on GitHub', loc_value)

    repos_value = f'{REPO_COUNT} {{Contributed: {REPO_COUNT}}} | Stars: {STAR_COUNT}'
    repos_dots = dots('Repos', repos_value)

    lines = [
        f'<tspan x="390" y="30">mohsen@dastaran</tspan>{sep}',
        row(50, 'OS', '<tspan class="key" y="50">OS</tspan>', 'Linux, Windows'),
        row(70, "Mohsen's Uptime", '<tspan class="key" y="70">Mohsen\'s Uptime</tspan>', MOHSEN_UPTIME, 'mohsen_uptime_data'),
        row(90, 'GitHub Uptime', '<tspan class="key" y="90">GitHub Uptime</tspan>', '5 years, 7 months, 5 days', 'age_data'),
        row(110, 'Host', '<tspan class="key" y="110">Host</tspan>', 'Planet Earth (Remote OK)'),
        row(130, 'Kernel', '<tspan class="key" y="130">Kernel</tspan>', 'Coffee-Powered Human'),
        row(150, 'IDE', '<tspan class="key" y="150">IDE</tspan>', 'VS Code, Cursor'),
        '<tspan x="390" y="170" class="cc">. </tspan>\n',
        row(190, 'Languages.Programming', '<tspan class="key" y="190">Languages</tspan>.<tspan class="key" y="190">Programming</tspan>', 'Rust, TypeScript, JavaScript'),
        row(210, 'Languages.Frameworks', '<tspan class="key" y="210">Languages</tspan>.<tspan class="key" y="210">Frameworks</tspan>', 'Vue, Nuxt, React Native'),
        '<tspan x="390" y="230" class="cc">. </tspan>\n',
        row(250, 'Hobbies', '<tspan class="key" y="250">Hobbies</tspan>', 'Guitar, Movies and Music'),
        row(270, 'Interests', '<tspan class="key" y="270">Interests</tspan>', 'Late-Night Coding, Open Source Dev'),
        f'<tspan x="390" y="310">{contact_sep}',
        row(330, 'Email', '<tspan class="key" y="330">Email</tspan>', 'mohsen.dastaran@gmail.com'),
        row(350, 'GitHub', '<tspan class="key" y="350">GitHub</tspan>', 'github.com/MohsenDastaran'),
        row(370, 'LinkedIn', '<tspan class="key" y="370">LinkedIn</tspan>', 'linkedin.com/in/mohsendastaran'),
        row(390, 'Portfolio', '<tspan class="key" y="390">Portfolio</tspan>', 'mohsendastaran.netlify.app'),
        row(410, 'Telegram', '<tspan class="key" y="410">Telegram</tspan>', 't.me/MohsenDastaran'),
        '<tspan x="390" y="430" class="cc">. </tspan>\n',
        f'<tspan x="390" y="450">{stats_sep}',
        (
            f'<tspan x="390" y="470" class="cc">. </tspan><tspan class="key" y="470">Repos</tspan>:'
            f'<tspan class="cc" id="repos_line_dots">{repos_dots}</tspan>'
            f'<tspan y="470" text-anchor="end" x="{RX}" class="value">'
            f'<tspan id="repo_data">{REPO_COUNT}</tspan> '
            '{<tspan class="key">Contributed</tspan>: <tspan id="contrib_data">' + str(REPO_COUNT) + '</tspan>} | '
            f'<tspan class="key">Stars</tspan>: <tspan id="star_data">{STAR_COUNT}</tspan></tspan>\n'
        ),
        row(490, 'Followers', '<tspan class="key" y="490">Followers</tspan>', str(FOLLOWER_COUNT), 'follower_data'),
        (
            f'<tspan x="390" y="510" class="cc">. </tspan>'
            f'<tspan class="key" y="510">Lines of Code on GitHub</tspan>:'
            f'<tspan class="cc" id="loc_line_dots">{loc_dots}</tspan>'
            f'<tspan y="510" text-anchor="end" x="{RX}" class="value">'
            f'<tspan id="loc_data">0</tspan> ( '
            f'<tspan class="addColor" id="loc_add">0</tspan><tspan class="addColor">++</tspan>, '
            f'<tspan class="delColor" id="loc_del">0</tspan><tspan class="delColor">--</tspan> )</tspan>\n'
        ),
    ]
    return '<text x="390" y="30" fill="' + text_fill + '">\n' + ''.join(lines) + '</text>'


def image_tag():
    existing = (ROOT / 'dark_mode.svg').read_text(encoding='utf-8') if (ROOT / 'dark_mode.svg').exists() else ''
    match = re.search(r'<image href="(data:image/png;base64,[^"]+)"[^>]*/>', existing)
    if match:
        href = match.group(1)
    else:
        href = 'data:image/png;base64,' + base64.b64encode((ROOT / 'ascii-art.png').read_bytes()).decode()
    return f'<image href="{href}" x="15" y="15" width="360" height="447" preserveAspectRatio="xMidYMid meet"/>'


def main():
    img = image_tag()
    for name, bg, text_fill, key, value, add, del_, cc in [
        ('dark_mode.svg', '#161b22', '#c9d1d9', '#ffa657', '#a5d6ff', '#3fb950', '#f85149', '#616e7f'),
        ('light_mode.svg', '#f6f8fa', '#24292f', '#953800', '#0a3069', '#1a7f37', '#cf222e', '#c2cfde'),
    ]:
        content = f"""<?xml version='1.0' encoding='UTF-8'?>
<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" font-family="ConsolasFallback,Consolas,monospace" width="985px" height="530px" font-size="16px">
<style>
@font-face {{src: local('Consolas'), local('Consolas Bold'); font-family: 'ConsolasFallback'; font-display: swap; -webkit-size-adjust: 109%; size-adjust: 109%;}}
.key {{fill: {key};}} .value {{fill: {value};}} .addColor {{fill: {add};}} .delColor {{fill: {del_};}} .cc {{fill: {cc};}}
text, tspan {{white-space: pre;}}
</style>
<rect width="985px" height="530px" fill="{bg}" rx="15"/>
{img}
{build_text(text_fill)}
</svg>
"""
        (ROOT / name).write_text(content, encoding='utf-8')
        print('Wrote', name)


if __name__ == '__main__':
    main()
