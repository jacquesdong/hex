#!/usr/bin/env python3
r"""hd (``hexdump -C``) 风格的字节转储工具。

偏移量列 + 十六进制（每 8 字节分组）+ ASCII 侧栏，ASCII 列左缘始终对齐。
默认连续折行（等同 hd）；``--split-lines`` 改为按数据自身换行断行。
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Sequence
from pathlib import Path

DEFAULT_WIDTH = 16
WIDTH_RANGE = (1, 256)
_GROUP = 8
_PRINTABLE = (0x20, 0x7E)


def _split_lines(data: bytes) -> list[bytes]:
    r"""按 ``\r\n`` / ``\n`` 切分（保留行尾换行字节），不含换行的尾段也返回。"""
    if not data:
        return []
    lines = re.split(rb'(?<=\n)', data)
    if lines and lines[-1] == b'':
        lines.pop()
    return lines


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


def _ascii_of(chunk: bytes, *, drop_line_endings: bool = False) -> str:
    """ASCII 侧栏：可打印原样、其余 ``.``；换行切分模式下丢掉行尾的 CR/LF。"""
    body = (
        chunk.rstrip(b'\r\n')
        if drop_line_endings and chunk.endswith((b'\r', b'\n'))
        else chunk
    )
    low, high = _PRINTABLE
    return ''.join(chr(byte) if low <= byte <= high else '.' for byte in body)


def hexdump(
    data: bytes,
    width: int = DEFAULT_WIDTH,
    offset: int = 0,
    *,
    split_lines: bool = False,
) -> str:
    r"""把字节渲染为 hd (``hexdump -C``) 风格的文本。

    默认**连续**折行（与 hd 一样：不看数据里的换行）；``split_lines=True`` 时改为
    按数据自身的 ``\r\n`` / ``\n`` 断行 —— 一行 = 报文里的一行，行尾换行字节只进
    hex 区、不进 ASCII 栏（即 ``sock_proxy.py`` 里 `hexdump` 的行为）。

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

    >>> print(hexdump(b'AB\r\n', width=16, split_lines=True))
    00000000  41 42 0d 0a                                       |AB|

    >>> print(hexdump(b'POST / HTTP/1.1\r\n\r\nnull'))
    00000000  50 4f 53 54 20 2f 20 48  54 54 50 2f 31 2e 31 0d  |POST / HTTP/1.1.|
    00000010  0a 0d 0a 6e 75 6c 6c                              |...null|

    >>> print(hexdump(b'POST / HTTP/1.1\r\n\r\nnull', split_lines=True))
    00000000  50 4f 53 54 20 2f 20 48  54 54 50 2f 31 2e 31 0d  |POST / HTTP/1.1|
    00000010  0a                                                ||
    00000011  0d 0a                                             ||
    00000013  6e 75 6c 6c                                       |null|

    >>> hexdump(b'')
    ''
    """
    if not WIDTH_RANGE[0] <= width <= WIDTH_RANGE[1]:
        raise ValueError(f'width 必须在 {WIDTH_RANGE[0]}..{WIDTH_RANGE[1]} 之间，收到 {width}')
    field = _hex_field_width(width)
    blocks = _split_lines(data) if split_lines else ([data] if data else [])
    rows: list[str] = []
    pos = 0
    for block in blocks:
        for start in range(0, len(block), width):
            chunk = block[start : start + width]
            hex_text = _hex_field(chunk).ljust(field)
            rows.append(
                f'{offset + pos:08x}  {hex_text}  '
                f'|{_ascii_of(chunk, drop_line_endings=split_lines)}|'
            )
            pos += len(chunk)
    return '\n'.join(rows)


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
    parser.add_argument(
        '-s',
        '--split-lines',
        action='store_true',
        help=r'按数据自身的 \r\n/\n 断行（默认连续折行，等同 hd）',
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
    """
    parser = _parser()
    args = parser.parse_args(argv)
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
    text = hexdump(data, width=args.width, offset=args.offset, split_lines=args.split_lines)
    if text:
        sys.stdout.write(text + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
