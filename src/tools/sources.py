"""
引用来源登记处（步骤 5 + 步骤 6）

作用：给每个来源分配一个编号 [1] [2] [3] ...，并自动去重。

为什么需要"登记处"？
  一次研究过程中会搜索很多次，同一个网页可能被多次搜到。
  如果不做去重，参考文献列表里会出现大量重复条目。
  如果不做编号，报告里就没法用 [n] 标注"这句话来自哪个来源"。

  所以 SourceRegistry 干三件事：
    1. 去重：同一个 URL（或标题相同）只登记一次
    2. 编号：第一次出现的来源，按顺序拿到 1、2、3 ...
    3. 查询：支持"这个来源见过没"的判断（步骤 6 去重要用）

  这样报告正文里的 [3] 和文末参考文献的第 3 条，就一定能对应上。

步骤 6 新增能力：
  在真正抓取网页之前，先用 is_seen() 判断"这条结果是不是已经见过"。
  如果见过就跳过——省下一次网络抓取、省一次压缩的 LLM 调用。
"""
import re

from src.models import Citation


def _normalize_title(title: str) -> str:
    """
    把标题"归一化"，便于判断两个标题是否相同。

    做法：去掉所有空白和标点，转成小写。
      "AI Agent 的未来！"  →  "aiagent的未来"
      "AI agent的未来"     →  "aiagent的未来"   ← 两者判为相同

    注意：这是"简单去重"，只能识别这种字面差异。
      更严谨的做法是用 embedding 算语义相似度，但那属于进阶内容。
    """
    # \s 是空白，\W 是非单词字符（标点等），+ 表示连续多个一起替换
    return re.sub(r"[\s\W_]+", "", title).lower()


class SourceRegistry:
    """来源登记处：负责编号与去重。"""

    def __init__(self) -> None:
        # 按"首次出现顺序"保存所有来源
        self._items: list[Citation] = []
        # URL -> 编号 的映射，用来快速判断"这个链接是不是已经登记过了"
        self._url_to_number: dict[str, int] = {}
        # 已登记标题的归一化集合，用来做"标题重复"判断
        self._titles: set[str] = set()

    def is_seen(self, url: str, title: str = "") -> bool:
        """
        判断一个来源是否"已经见过"（URL 相同 或 标题相同）。

        用途：在抓取网页之前先判断，见过就跳过，避免重复劳动。
        """
        if url and url in self._url_to_number:
            return True
        if title and _normalize_title(title) in self._titles:
            return True
        return False

    def add(self, citation: Citation) -> int:
        """
        登记一个来源，返回它的编号。

        如果这个 URL 之前登记过，直接返回原来的编号（去重）；
        否则追加到列表末尾，并返回新的编号（从 1 开始）。
        """
        url = citation.url
        if url and url in self._url_to_number:
            # 已登记过：返回原编号，不重复添加
            return self._url_to_number[url]

        self._items.append(citation)
        number = len(self._items)  # 编号从 1 开始，正好等于列表长度
        if url:
            self._url_to_number[url] = number
        if citation.title:
            self._titles.add(_normalize_title(citation.title))
        return number

    def items(self) -> list[Citation]:
        """返回所有已登记来源（按编号顺序）。"""
        return list(self._items)

    def __len__(self) -> int:
        # 实现 __len__ 后，就能对实例直接用 len(registry) 取来源数量
        return len(self._items)
