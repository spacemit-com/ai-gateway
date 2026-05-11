"""llama-server 启动参数合并和去重工具。"""


def merge_and_dedup_args(
    default_args: list[str] | None,
    user_args: list[str] | None,
) -> list[str]:
    """合并并去重 llama-server 启动参数。

    优先级：用户参数 > 配置参数

    Args:
        default_args: 配置文件中的 default_args
        user_args: 用户请求时传入的 extra_args

    Returns:
        去重后的参数列表

    Examples:
        >>> merge_and_dedup_args(
        ...     ["--threads", "8", "--embedding"],
        ...     ["--threads", "16"]
        ... )
        ['--threads', '16', '--embedding']
    """
    # 1. 合并参数：配置 + 用户（用户参数在后，优先级高）
    merged = []
    if default_args:
        merged.extend(default_args)
    if user_args:
        merged.extend(user_args)

    # 2. 去重：保留最后出现的值
    return _dedup_args(merged)


def _dedup_args(args: list[str]) -> list[str]:
    """去重参数，保留最后出现的值。

    处理两种形式：
    - 键值对：--key value（如 --threads 8）
    - 布尔标志：--flag（如 --embedding）

    Args:
        args: 原始参数列表

    Returns:
        去重后的参数列表，保留每个键的最后一次出现
    """
    seen = {}  # key -> (key, value?) 或 key -> (key,)
    i = 0

    while i < len(args):
        arg = args[i]

        if arg.startswith("--") or arg.startswith("-"):
            # 检查下一个是否是值（不以 - 开头）
            if i + 1 < len(args) and not args[i + 1].startswith("-"):
                # 键值对：--key value
                key = arg
                value = args[i + 1]
                seen[key] = (key, value)
                i += 2
            else:
                # 布尔标志：--flag
                seen[arg] = (arg,)
                i += 1
        else:
            # 孤立的值（不应该出现，跳过）
            i += 1

    # 重建参数列表
    result = []
    for item in seen.values():
        result.extend(item)

    return result
