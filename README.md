# hex.py

`hd`（`hexdump -C`）风格的字节转储/还原工具，纯 Python 单文件实现。

## 特色

- **支持按换行切分**（`-s`）：默认像 `hd` 连续折行；加 `-s` 后按数据自身的 `\r\n` / `\n` 断行，一行就是报文里的一行，行尾换行字节只进 hex 区。还可用 `-d` 指定任意分隔符作为行边界。
- **支持自定义折行宽度**（`-w`）：1..256 可调，ASCII 侧栏始终固定在同一列；`-p` 模式下 `-w 0` 表示不折行。
- **正反双向**：`-r` 把 hexdump 还原成原始字节，兼容 `hexdump -C`、`xxd -g1`、`od -tx1` / `-tx1z`。
- 纯 Python 单文件、无运行时依赖；uv 管理 pytest / ruff / mypy。

## 运行

需要 Python ≥ 3.11 与 [uv](https://docs.astral.sh/uv/)。

```sh
printf 'hello\nworld\n' | uv run hex.py
uv run hex.py FILE
uv run hex.py --help
```

## 正向：转储

默认输出等同 `hd` 的观感：8 位偏移 + 十六进制（每 8 字节分组）+ ASCII 侧栏，每行 16 字节。

```
$ printf 'hello\nworld\n' | uv run hex.py
00000000  68 65 6c 6c 6f 0a 77 6f  72 6c 64 0a              |hello.world.|
```

- `-w N`：折行宽度（1..256，默认 16）；`-p` 下可用 `0` 表示不折行。
- `-s / --split`：按数据自身的 `\r\n` / `\n` 断行；行尾换行只进 hex 区，不进 ASCII 栏。
- `-d / --delimiter PATTERN`：按任意字节序列标注行边界，分隔符仍保留在 hex 区；支持 `\r`、`\n`、`\t`、`\xNN`、`\\` 转义。与 `-s` 互斥。
- `-o / --offset N`：起始偏移；`-n / --length N`：只读取前 N 字节。
- `-p / --plain`：纯 hex 输出（无偏移/ASCII），每行字节数由 `-w` 控制，`-w 0` 不折行；与 `-s`/`-d`/`-o` 互斥。

数值参数支持 `0x` 十六进制、`0b` 二进制、`0o` 八进制；**前导 `0` 按八进制**（如 `016` = 14），其余十进制。

```
$ printf 'abcdef' | uv run hex.py -p -w 4
61626364
6566
```

## 反向：还原

`-r / --revert` 从 stdin 或 FILE 读取 hexdump 文本，把原始字节写到 stdout。

```
$ head -c 60 /bin/sh | hexdump -C | uv run hex.py -r | wc -c
60
$ printf '616263\n' | uv run hex.py -r -p
abc
```

支持的输入格式：本工具输出、`hexdump -C`、`xxd -g1`、`od -tx1`、`od -tx1z`。

- 偏移列只检查形状、忽略其值（所以 `od` 的八进制偏移也能读）；ASCII 栏被忽略。
- 每行字节数可变。
- **不支持**：传统 `hexdump` 的 4 位字（如 `457f`，请用 `hexdump -C`）、无偏移行（属于 `-p`）、`*` 折叠行（`hexdump`/`od` 加 `-v`，`xxd` 去掉 `-a`）。这些情况都会明确报错。
- `-r` 只能与 `-p` 组合，不能带其它选项。

## 开发

```sh
uv run --group dev python -m doctest hex.py
uv run --group dev pytest -q
uv run --group dev ruff check .
uv run --group dev mypy
```

文件：`hex.py`（核心 + CLI）、`tests/test_hex.py`、`pyproject.toml`、`uv.lock`。项目约定 UTF-8 / LF（见 `.editorconfig`）。
