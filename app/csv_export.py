"""CSV 导出：统一的编码、换行与转义规则。

单独成模块，是因为「UTF-8 BOM」「CRLF」「公式注入转义」这三件事任何一处写错，
导出的文件在 Excel 里就会变成乱码或直接执行公式，而这类问题在接口测试里很容易漏掉。
"""

import csv
import io
import urllib.parse
from collections.abc import Iterable, Sequence

from fastapi import Response

# Excel 只有看到开头的 UTF-8 BOM 才会按 UTF-8 解码，否则中文全是乱码。
UTF8_BOM = "\ufeff"

# 这些开头的单元格会被 Excel / WPS 当成公式，导出的资料标题或审计详情里
# 只要出现一个 "=..." 就会变成「打开即执行」。
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def escape_cell(value: object) -> str:
    """把单元格转成文本，并中和公式注入。

    做法是在危险前缀前加一个半角单引号：Excel 会把它当「这是文本」的标记，
    显示时不会出现这个引号，但公式不会被求值。
    """

    if value is None:
        text = ""
    elif isinstance(value, bool):
        text = "是" if value else "否"
    else:
        text = str(value)
    if text.startswith(_FORMULA_PREFIXES):
        return "'" + text
    return text


def render_csv(header: Sequence[object], rows: Iterable[Sequence[object]]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow([escape_cell(cell) for cell in header])
    for row in rows:
        writer.writerow([escape_cell(cell) for cell in row])
    return (UTF8_BOM + buffer.getvalue()).encode("utf-8")


def csv_response(
    filename: str, header: Sequence[object], rows: Iterable[Sequence[object]]
) -> Response:
    """构造 CSV 下载响应。

    文件名可能有中文，所以用 RFC 5987 的 ``filename*`` 让浏览器正确解码，
    同时保留一个 ASCII 的 ``filename`` 给不认 ``filename*`` 的老客户端。
    """

    quoted = urllib.parse.quote(filename)
    return Response(
        content=render_csv(header, rows),
        media_type="text/csv",
        headers={
            "Content-Disposition": (
                f"attachment; filename=\"export.csv\"; filename*=UTF-8''{quoted}"
            )
        },
    )
