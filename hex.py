#!/usr/bin/env python3
r"""hd (``hexdump -C``) 风格的字节转储工具。

偏移量列 + 十六进制（每 8 字节分组）+ ASCII 侧栏，ASCII 列左缘始终对齐。
默认连续折行（等同 hd）；``--split`` 改为按数据自身换行断行。
"""

from __future__ import annotations

import argparse
import codecs
import re
import sys
from collections.abc import Sequence
from pathlib import Path

DEFAULT_WIDTH = 16
WIDTH_RANGE = (1, 256)
_GROUP = 8
_PRINTABLE = (0x20, 0x7E)
_DELIM_ESCAPE_RE = re.compile(r'\\(?:[\\rtn]|x[0-9a-fA-F]{2})')


def _split_by(data: bytes, delimiter: bytes) -> list[bytes]:
    r"""按 ``delimiter`` 切分并保留分隔符（附在前一段末尾），无分隔的尾段也返回。"""
    if not data:
        return []
    parts = data.split(delimiter)
    blocks = [part + delimiter for part in parts[:-1]]
    if parts[-1]:
        blocks.append(parts[-1])
    return blocks


def _hex_field(chunk: bytes) -> str:
    """十六进制区：每字节两位小写、空格分隔，每 8 字节多一个空格分组。"""
    groups = [
        ' '.join(f'{byte:02x}' for byte in chunk[i : i + _GROUP])
        for i in range(0, len(chunk), _GROUP)
    ]
    return '  '.join(groups)


def _hex_field_width(width: int) -> int:
    """整行（`width` 字节）的十六进制区宽度 —— ASCII 列按这个宽度固定对齐。"""
    return len(_hex_field(bytes(width)))


def _ascii_of(chunk: bytes, *, strip: bytes = b'') -> str:
    """ASCII 侧栏：可打印原样、其余 ``.``；行尾的 ``strip`` 分隔符不显示。"""
    body = chunk
    if strip and body.endswith(strip):
        body = body[: -len(strip)]
        if strip == b'\n':
            body = body.rstrip(b'\r')
    elif strip == b'\n' and body.endswith(b'\r'):
        body = body[:-1]
    low, high = _PRINTABLE
    return ''.join(chr(byte) if low <= byte <= high else '.' for byte in body)


def hexdump(
    data: bytes,
    width: int = DEFAULT_WIDTH,
    offset: int = 0,
    *,
    split: bool = False,
    delimiter: bytes | None = None,
) -> str:
    r"""把字节渲染为 hd (``hexdump -C``) 风格的文本。

    默认**连续**折行（与 hd 一样：不看数据里的换行）；``split=True`` 时改为
    按数据自身的 ``\r\n`` / ``\n`` 断行 —— 一行 = 报文里的一行，行尾换行字节只进
    hex 区、不进 ASCII 栏（即 ``sock_proxy.py`` 里 `hexdump` 的行为）。
    ``delimiter`` 可指定任意分隔符作为行边界（隐含 ``split``），分隔符同样只进 hex 区。

    十六进制区每 8 字节多一个空格分组，并一律补空格到**整行**（``width`` 字节）的
    字段宽，所以 ASCII 侧栏左缘固定在同一列；补白在中间，行尾不留空白。返回值按行
    以 ``\n`` 分隔、**末尾不带换行**（由 IO 层负责补）。

    >>> print(hexdump(b'abcdefghijklmnop'))
    00000000  61 62 63 64 65 66 67 68  69 6a 6b 6c 6d 6e 6f 70  |abcdefghijklmnop|

    >>> print(hexdump(b'abcdefghij', width=4, offset=0x10))
    00000010  61 62 63 64  |abcd|
    00000014  65 66 67 68  |efgh|
    00000018  69 6a        |ij|

    >>> print(hexdump(b'\x00\x01\xff', width=8))
    00000000  00 01 ff                 |...|

    >>> print(hexdump(b'AB\r\n', width=16, split=True))
    00000000  41 42 0d 0a                                       |AB|

    >>> print(hexdump(b'a,b,', width=4, delimiter=b','))
    00000000  61 2c        |a|
    00000002  62 2c        |b|

    >>> print(hexdump(b'POST / HTTP/1.1\r\n\r\nnull'))
    00000000  50 4f 53 54 20 2f 20 48  54 54 50 2f 31 2e 31 0d  |POST / HTTP/1.1.|
    00000010  0a 0d 0a 6e 75 6c 6c                              |...null|

    >>> print(hexdump(b'POST / HTTP/1.1\r\n\r\nnull', split=True))
    00000000  50 4f 53 54 20 2f 20 48  54 54 50 2f 31 2e 31 0d  |POST / HTTP/1.1|
    00000010  0a                                                ||
    00000011  0d 0a                                             ||
    00000013  6e 75 6c 6c                                       |null|

    >>> hexdump(b'')
    ''
    """
    if not WIDTH_RANGE[0] <= width <= WIDTH_RANGE[1]:
        raise ValueError(f'width 必须在 {WIDTH_RANGE[0]}..{WIDTH_RANGE[1]} 之间，收到 {width}')
    boundary = delimiter if delimiter is not None else (b'\n' if split else None)
    if boundary is not None and not boundary:
        raise ValueError('delimiter 不能为空')
    field = _hex_field_width(width)
    blocks = _split_by(data, boundary) if boundary else ([data] if data else [])
    rows: list[str] = []
    pos = 0
    for block in blocks:
        for start in range(0, len(block), width):
            chunk = block[start : start + width]
            hex_text = _hex_field(chunk).ljust(field)
            rows.append(
                f'{offset + pos:08x}  {hex_text}  '
                f'|{_ascii_of(chunk, strip=boundary or b"")}|'
            )
            pos += len(chunk)
    return '\n'.join(rows)


def unhexdump(data: bytes | str) -> bytes:
    r"""把 hexdump 文本还原为字节；偏移列与 ASCII 栏都被忽略。

    兼容本工具的输出、``hexdump -C``、``xxd -g1``、``od -tx1`` 与 ``od -tx1z``。

    格式规则：偏移是 6..16 位 hex、可带尾部冒号；其值不解释，所以 ``od`` 的八进制
    偏移也能读。其后每个「恰好两位 hex」的 token 是一个字节，遇到第一个其它 token
    （ASCII 栏起点）即停止，余下整行忽略。每行字节数可变。

    以下输入会报错：传统 ``hexdump`` 的 4 位字（请用 ``hexdump -C``）、无偏移行
    （属于 ``-p``），以及 ``hexdump``/``od``/``xxd`` 的 ``*`` 折叠行——展开折叠
    需要解释偏移值，而这里刻意忽略偏移。避免折叠：``hexdump``/``od`` 加 ``-v``，
    ``xxd`` 去掉 ``-a``。

    各工具的折叠规则不同：``hexdump``/``od`` 压缩任意重复行，``xxd -a`` 只压缩
    全零行；``xxd -r`` 能借偏移列展开自己的 ``*``，但跨工具的 ``*`` 不可靠。

    另外，ASCII 栏若恰好以两位 hex 形式的 token 开头，会被误读为一个字节。

    >>> unhexdump(b'00000000  61 62 63  |abc|\n')
    b'abc'
    >>> unhexdump(b'00000000: 7f 45  |.E|\n')
    b'\x7fE'
    >>> unhexdump(b'000000 7f 45  >.E<\n')
    b'\x7fE'
    >>> unhexdump(hexdump(b'POST / HTTP/1.1\r\n\r\nnull')) == b'POST / HTTP/1.1\r\n\r\nnull'
    True
    """
    if isinstance(data, str):
        try:
            data = data.encode('ascii')
        except UnicodeEncodeError as exc:
            raise ValueError('hexdump 文本必须是 ASCII') from exc
    out = bytearray()
    for raw_line in data.splitlines():
        tokens = raw_line.split()
        if not tokens:
            continue
        if tokens[0] == b'*':
            raise ValueError('不支持 hexdump/od/xxd 的 * 折叠行（hexdump/od 加 -v，xxd 去掉 -a）')
        if not re.fullmatch(rb'[0-9a-fA-F]{6,16}:?', tokens[0]):
            raise ValueError(f'无法解析 revert 行：{raw_line!r}')
        line_bytes = bytearray()
        for token in tokens[1:]:
            if not re.fullmatch(rb'[0-9a-fA-F]{2}', token):
                break
            line_bytes.append(int(token, 16))
        if not line_bytes and len(tokens) > 1:
            raise ValueError(f'无法解析 revert 行（需要两位一组的 hex 字节）：{raw_line!r}')
        out.extend(line_bytes)
    return bytes(out)


def _width(text: str) -> int:
    """`--width` 取值校验（1..256）。"""
    value = int(text)
    if not WIDTH_RANGE[0] <= value <= WIDTH_RANGE[1]:
        raise argparse.ArgumentTypeError(
            f'width 必须在 {WIDTH_RANGE[0]}..{WIDTH_RANGE[1]} 之间，收到 {value}'
        )
    return value


def _offset(text: str) -> int:
    """`--offset` 取值校验（支持 ``0x`` 前缀）。"""
    try:
        value = int(text, 0)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f'offset 无效：{text!r}') from exc
    if value < 0:
        raise argparse.ArgumentTypeError('offset 不能为负')
    return value


def _length(text: str) -> int:
    """`--length` 取值校验（非负整数）。"""
    value = int(text)
    if value < 0:
        raise argparse.ArgumentTypeError(f'length 不能为负：{value}')
    return value


def _delimiter(text: str) -> bytes:
    """`--delimiter` 取值校验：把 ``\\r`` / ``\\xNN`` 等转义解码为字节。"""
    if not text:
        raise argparse.ArgumentTypeError('delimiter 不能为空')
    if '\\' in _DELIM_ESCAPE_RE.sub('', text):
        raise argparse.ArgumentTypeError(f'delimiter 含无效转义：{text!r}')
    if any(ord(char) > 0x7F for char in text):
        raise argparse.ArgumentTypeError('delimiter 只接受 ASCII 字符')
    return codecs.decode(text, 'unicode_escape').encode('latin-1')


def _parser() -> argparse.ArgumentParser:
    """构造 CLI 参数解析器。"""
    parser = argparse.ArgumentParser(
        prog='hex.py',
        description='hd (hexdump -C) 风格的字节转储：偏移量 + 十六进制 + ASCII 侧栏',
    )
    parser.add_argument(
        'file', nargs='?', metavar='FILE', help='输入文件（省略则从 stdin 读）'
    )
    parser.add_argument(
        '-w',
        '--width',
        type=_width,
        default=DEFAULT_WIDTH,
        metavar='N',
        help=f'折行宽度（{WIDTH_RANGE[0]}..{WIDTH_RANGE[1]}，默认 {DEFAULT_WIDTH}）',
    )
    boundaries = parser.add_mutually_exclusive_group()
    boundaries.add_argument(
        '-s',
        '--split',
        action='store_true',
        help=r'按数据自身的 \r\n/\n 断行',
    )
    boundaries.add_argument(
        '-d',
        '--delimiter',
        type=_delimiter,
        metavar='PATTERN',
        help=r'按 PATTERN 标注行边界（保留在 hex 区），支持 \r \n \t \xNN \\ 转义',
    )
    parser.add_argument(
        '-o',
        '--offset',
        type=_offset,
        default=0,
        metavar='N',
        help='起始偏移，支持 0x 前缀（默认 0）',
    )
    parser.add_argument(
        '-n',
        '--length',
        type=_length,
        metavar='N',
        help='只读取前 N 个字节（默认全部）',
    )
    parser.add_argument(
        '-r',
        '--revert',
        action='store_true',
        help='反向模式：把 hexdump 文本还原为原始字节写到 stdout',
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    r"""CLI 入口：从文件或 stdin 读字节，按 hd 风格写到 stdout。

    >>> _width('16')
    16
    >>> _offset('0x10')
    16
    >>> _offset('16')
    16
    >>> _length('4')
    4
    >>> _delimiter(r'\r\n')
    b'\r\n'
    """
    parser = _parser()
    args = parser.parse_args(argv)
    if args.revert and any(
        (
            args.width != DEFAULT_WIDTH,
            args.split,
            args.delimiter is not None,
            args.offset != 0,
            args.length is not None,
        )
    ):
        parser.error('--revert 不能与其它选项同时使用')
    try:
        if args.file:
            with Path(args.file).open('rb') as stream:
                data = stream.read(args.length) if args.length is not None else stream.read()
        else:
            data = (
                sys.stdin.buffer.read(args.length)
                if args.length is not None
                else sys.stdin.buffer.read()
            )
    except OSError as exc:
        parser.error(str(exc))
    if args.revert:
        try:
            raw = unhexdump(data)
        except ValueError as exc:
            parser.error(str(exc))
        sys.stdout.buffer.write(raw)
        return 0
    text = hexdump(
        data,
        width=args.width,
        offset=args.offset,
        split=args.split,
        delimiter=args.delimiter,
    )
    if text:
        sys.stdout.write(text + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
