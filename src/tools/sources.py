"""
引用来源登记处（步骤 5）

作用：给每个来源分配一个编号 [1] [2] [3] ...，并按 URL 自动去重。

为什么需要"登记处"？
  一次研究过程中会搜索很多次，同一个网页可能被多次搜到。
  如果不做去重，参考文献列表里会出现大量重复条目。
  如果不做编号，报告里就没法用 [n] 标注"这句话来自哪个来源"。

  所以 SourceRegistry 干两件事：
    1. 去重：同一个 URL 只登记一次，重复登记时返回原编号
    2. 编号：第一次出现的来源，按顺序拿到 1、2、3 ...

  这样报告正文里的 [3] 和文末参考文献的第 3 条，就一定能对应上。
"""
from src.models import Citation


class SourceRegistry:
    """来源登记处：负责编号与去重。"""

    def __init__(self) -> None:
        # 按"首次出现顺序"保存所有来源
        self._items: list[Citation] = []
        # URL -> 编号 的映射，用来快速判断"这个链接是不是已经登记过了"
        self._url_to_number: dict[str, int] = {}

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
        return number

    def items(self) -> list[Citation]:
        """返回所有已登记来源（按编号顺序）。"""
        return list(self._items)

    def __len__(self) -> int:
        # 实现 __len__ 后，就能对实例直接用 len(registry) 取来源数量
        return len(self._items)