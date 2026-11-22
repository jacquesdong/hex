from __future__ import annotations

import io
from pathlib import Path

import pytest

from hex import hexdump, main


def test_default_is_hd_style() -> None:
    assert hexdump(b'hello\nworld\n') == (
        '00000000  68 65 6c 6c 6f 0a 77 6f  72 6c 64 0a              |hello.world.|'
    )


def test_split_keeps_line_endings_out_of_ascii() -> None:
    assert hexdump(b'AB\r\n', split=True) == (
        '00000000  41 42 0d 0a                                       |AB|'
    )


def test_width_and_offset() -> None:
    assert hexdump(b'abcdefghij', width=4, offset=0x10) == (
        '00000010  61 62 63 64  |abcd|\n'
        '00000014  65 66 67 68  |efgh|\n'
        '00000018  69 6a        |ij|'
    )


def test_non_printable_bytes() -> None:
    assert hexdump(b'\x00\x01\xff', width=8) == (
        '00000000  00 01 ff                 |...|'
    )


def test_empty_input() -> None:
    assert hexdump(b'') == ''


@pytest.mark.parametrize('width', [0, -1, 257])
def test_invalid_width_raises(width: int) -> None:
    with pytest.raises(ValueError, match=r'width.*1\.\.256'):
        hexdump(b'x', width=width)


def test_main_reads_stdin(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stream = io.TextIOWrapper(io.BytesIO(b'abc'))
    monkeypatch.setattr('sys.stdin', stream)
    assert main([]) == 0
    assert capsys.readouterr().out == (
        '00000000  61 62 63                                          |abc|\n'
    )


def test_main_reads_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / 'sample.bin'
    path.write_bytes(b'xyz')
    assert main([str(path)]) == 0
    assert capsys.readouterr().out == (
        '00000000  78 79 7a                                          |xyz|\n'
    )


def test_main_options(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stream = io.TextIOWrapper(io.BytesIO(b'AB\r\n'))
    monkeypatch.setattr('sys.stdin', stream)
    assert main(['-s', '-o', '0x10']) == 0
    assert capsys.readouterr().out == (
        '00000010  41 42 0d 0a                                       |AB|\n'
    )


def test_main_rejects_bad_width(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(['-w', '0'])
    assert exc.value.code == 2
    assert 'width' in capsys.readouterr().err


def test_main_reports_missing_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / 'missing.bin'
    with pytest.raises(SystemExit) as exc:
        main([str(missing)])
    assert exc.value.code == 2
    assert 'No such file' in capsys.readouterr().err


def test_main_length_limits_stdin(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stream = io.TextIOWrapper(io.BytesIO(b'abcdefghij'))
    monkeypatch.setattr('sys.stdin', stream)
    assert main(['-n', '4']) == 0
    assert capsys.readouterr().out == (
        '00000000  61 62 63 64                                       |abcd|\n'
    )


def test_main_length_zero_produces_no_output(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stream = io.TextIOWrapper(io.BytesIO(b'abc'))
    monkeypatch.setattr('sys.stdin', stream)
    assert main(['-n', '0']) == 0
    assert capsys.readouterr().out == ''


def test_main_length_with_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / 'sample.bin'
    path.write_bytes(b'abcdef')
    assert main(['--length', '3', str(path)]) == 0
    assert capsys.readouterr().out == (
        '00000000  61 62 63                                          |abc|\n'
    )


def test_main_length_with_split(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stream = io.TextIOWrapper(io.BytesIO(b'AB\r\nCD\r\n'))
    monkeypatch.setattr('sys.stdin', stream)
    assert main(['-n', '3', '-s']) == 0
    assert capsys.readouterr().out == (
        '00000000  41 42 0d                                          |AB|\n'
    )


def test_main_long_split_option(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stream = io.TextIOWrapper(io.BytesIO(b'AB\r\n'))
    monkeypatch.setattr('sys.stdin', stream)
    assert main(['--split']) == 0
    assert capsys.readouterr().out == (
        '00000000  41 42 0d 0a                                       |AB|\n'
    )


def test_main_rejects_negative_length(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(['--length=-1'])
    assert exc.value.code == 2
    assert 'length' in capsys.readouterr().err


def test_main_delimiter_keeps_bytes_in_hex(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stream = io.TextIOWrapper(io.BytesIO(b'a,b,'))
    monkeypatch.setattr('sys.stdin', stream)
    assert main(['-d', ',']) == 0
    assert capsys.readouterr().out == (
        '00000000  61 2c                                             |a|\n'
        '00000002  62 2c                                             |b|\n'
    )


def test_main_delimiter_escape(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stream = io.TextIOWrapper(io.BytesIO(b'a\x00b'))
    monkeypatch.setattr('sys.stdin', stream)
    assert main(['-d', r'\x00']) == 0
    assert capsys.readouterr().out == (
        '00000000  61 00                                             |a|\n'
        '00000002  62                                                |b|\n'
    )


def test_main_split_and_delimiter_are_mutually_exclusive(
    capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exc:
        main(['-s', '-d', ','])
    assert exc.value.code == 2
    assert 'not allowed' in capsys.readouterr().err


def test_main_rejects_bad_delimiter(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(['-d', r'\q'])
    assert exc.value.code == 2
    assert 'delimiter' in capsys.readouterr().err


def test_main_rejects_empty_delimiter(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(['-d', ''])
    assert exc.value.code == 2


def test_hexdump_rejects_empty_delimiter() -> None:
    with pytest.raises(ValueError, match='delimiter'):
        hexdump(b'x', delimiter=b'')
