from __future__ import annotations

import io
from pathlib import Path

import pytest

from hex import hexdump, hexplain, main, unhexdump, unhexplain


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


@pytest.mark.parametrize(
    'payload',
    [b'abc', b'POST / HTTP/1.1\r\n\r\nnull', bytes(range(256)), b''],
)
def test_unhexdump_roundtrip(payload: bytes) -> None:
    assert unhexdump(hexdump(payload)) == payload


def test_unhexdump_ignores_offset_gaps() -> None:
    dump = (
        b'00000000  61 62                                             |ab|\n'
        b'00000010  78 79                                             |xy|\n'
    )
    assert unhexdump(dump) == b'abxy'


def test_unhexdump_skips_offset_only_line() -> None:
    dump = b'00000000  61 62  |ab|\n00000002\n'
    assert unhexdump(dump) == b'ab'


def test_unhexdump_accepts_xxd_output() -> None:
    dump = (
        b'00000000: 7f 45 4c 46 02 01 01 00 00 00 00 00 00 00 00 00  .ELF............\n'
        b'00000010: 03 00 3e 00 01 00 00 00 10 4f 00 00 00 00 00 00  ..>......O......\n'
    )
    assert unhexdump(dump) == bytes.fromhex(
        '7f 45 4c 46 02 01 01 00 00 00 00 00 00 00 00 00 '
        '03 00 3e 00 01 00 00 00 10 4f 00 00 00 00 00 00'
    )


def test_unhexdump_accepts_od_output() -> None:
    dump = (
        b'000000 7f 45 4c 46 02 01 01 00 00 00 00 00 00 00 00 00  >.ELF............<\n'
        b'000010 03 00 3e 00 01 00 00 00 10 4f 00 00 00 00 00 00  >..>......O......<\n'
        b'000020\n'
    )
    assert unhexdump(dump) == bytes.fromhex(
        '7f 45 4c 46 02 01 01 00 00 00 00 00 00 00 00 00 '
        '03 00 3e 00 01 00 00 00 10 4f 00 00 00 00 00 00'
    )


def test_unhexdump_accepts_octal_style_offsets() -> None:
    dump = b'0000000 7f 45 4c 46\n0000020 03 00 3e 00\n0000074\n'
    assert unhexdump(dump) == bytes.fromhex('7f 45 4c 46 03 00 3e 00')


def test_unhexdump_accepts_variable_bytes_per_line() -> None:
    dump = (
        b'0000000 7f 45 4c 46  >.ELF<\n'
        b'0000004 02 01 01 00  >....<\n'
        b'0000008\n'
    )
    assert unhexdump(dump) == bytes.fromhex('7f 45 4c 46 02 01 01 00')


def test_unhexdump_rejects_offsetless_line() -> None:
    with pytest.raises(ValueError, match='无法解析'):
        unhexdump(b'7f 45 4c 46\n')


def test_unhexdump_rejects_star_line() -> None:
    with pytest.raises(ValueError, match=r'hexdump/od/xxd.*-v.*-a'):
        unhexdump(b'00000000  00 00  |..|\n*\n00000040\n')


def test_unhexdump_rejects_malformed_line() -> None:
    with pytest.raises(ValueError, match='无法解析'):
        unhexdump(b'not a dump\n')


def test_unhexdump_rejects_non_ascii_text() -> None:
    with pytest.raises(ValueError, match='ASCII'):
        unhexdump('00000000  61 62  |ab|\n\xff')


def test_unhexdump_rejects_word_tokens() -> None:
    with pytest.raises(ValueError, match='hex 字节'):
        unhexdump(b'0000000 457f 464c 0102 0001\n')


def test_main_revert_rejects_word_dump(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stream = io.TextIOWrapper(io.BytesIO(b'0000000 457f 464c 0102 0001\n0000010\n'))
    monkeypatch.setattr('sys.stdin', stream)
    with pytest.raises(SystemExit) as exc:
        main(['-r'])
    assert exc.value.code == 2
    assert 'hex 字节' in capsys.readouterr().err


def test_main_revert_writes_raw_bytes(
    monkeypatch: pytest.MonkeyPatch, capsysbinary: pytest.CaptureFixture[bytes]
) -> None:
    stream = io.TextIOWrapper(io.BytesIO(hexdump(b'abc').encode('ascii')))
    monkeypatch.setattr('sys.stdin', stream)
    assert main(['-r']) == 0
    assert capsysbinary.readouterr().out == b'abc'


def test_main_revert_reads_file(
    tmp_path: Path, capsysbinary: pytest.CaptureFixture[bytes]
) -> None:
    path = tmp_path / 'dump.txt'
    path.write_bytes(hexdump(b'xyz').encode('ascii'))
    assert main(['--revert', str(path)]) == 0
    assert capsysbinary.readouterr().out == b'xyz'


def test_main_revert_rejects_other_options(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(['-r', '-w', '4'])
    assert exc.value.code == 2
    assert '--revert' in capsys.readouterr().err


def test_hexplain_lines() -> None:
    assert hexplain(b'abcdef', width=4) == '61626364\n6566'
    assert hexplain(b'') == ''


def test_unhexplain_ignores_whitespace() -> None:
    assert unhexplain(b'61 62\n63\t64') == b'abcd'
    assert unhexplain('6162') == b'ab'


def test_unhexplain_rejects_bad_input() -> None:
    with pytest.raises(ValueError, match='奇数'):
        unhexplain(b'616')
    with pytest.raises(ValueError, match='非法字符'):
        unhexplain(b'61 6z')


def test_plain_roundtrip() -> None:
    payload = bytes(range(256))
    assert unhexplain(hexplain(payload, width=7)) == payload


def test_main_plain_writes_hex(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stream = io.TextIOWrapper(io.BytesIO(b'abc'))
    monkeypatch.setattr('sys.stdin', stream)
    assert main(['-p']) == 0
    assert capsys.readouterr().out == '616263\n'


def test_main_plain_width(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stream = io.TextIOWrapper(io.BytesIO(b'abcdef'))
    monkeypatch.setattr('sys.stdin', stream)
    assert main(['-p', '-w', '4']) == 0
    assert capsys.readouterr().out == '61626364\n6566\n'


def test_main_revert_plain(
    monkeypatch: pytest.MonkeyPatch, capsysbinary: pytest.CaptureFixture[bytes]
) -> None:
    stream = io.TextIOWrapper(io.BytesIO(b'61 62\n63'))
    monkeypatch.setattr('sys.stdin', stream)
    assert main(['-r', '-p']) == 0
    assert capsysbinary.readouterr().out == b'abc'


def test_main_plain_rejects_boundary_options(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(['-p', '-s'])
    assert exc.value.code == 2
    assert '--plain' in capsys.readouterr().err


def test_main_accepts_prefixed_and_leading_zero_integers(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stream = io.TextIOWrapper(io.BytesIO(b'abcdef'))
    monkeypatch.setattr('sys.stdin', stream)
    assert main(['-w', '0x4', '-n', '0o6', '-o', '010']) == 0
    assert capsys.readouterr().out == (
        '00000008  61 62 63 64  |abcd|\n'
        '0000000c  65 66        |ef|\n'
    )
