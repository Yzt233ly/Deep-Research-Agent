"""
来源登记处（SourceRegistry）的单元测试（步骤 5 + 步骤 6）

测试重点：
  1. 编号是否从 1 开始、按顺序递增
  2. 相同 URL 是否去重（返回同一个编号）
  3. is_seen 能否识别"URL 相同"和"标题相同"
"""
from src.models import Citation
from src.tools import SourceRegistry


def test_add_assigns_increasing_numbers():
    """每次登记的编号应该依次是 1、2、3。"""
    registry = SourceRegistry()

    n1 = registry.add(Citation(title="文章A", url="https://a.com", summary="A"))
    n2 = registry.add(Citation(title="文章B", url="https://b.com", summary="B"))
    n3 = registry.add(Citation(title="文章C", url="https://c.com", summary="C"))

    assert (n1, n2, n3) == (1, 2, 3)
    assert len(registry) == 3


def test_same_url_is_deduplicated():
    """相同 URL 再次登记，应该返回原编号且不新增条目。"""
    registry = SourceRegistry()

    first = registry.add(Citation(title="文章A", url="https://a.com", summary="A"))
    again = registry.add(Citation(title="文章A（另一个标题）", url="https://a.com", summary="别的内容"))

    assert first == again == 1
    assert len(registry) == 1  # 没有被重复添加


def test_is_seen_by_url():
    """is_seen 应该能通过 URL 判断"见过"。"""
    registry = SourceRegistry()
    registry.add(Citation(title="文章A", url="https://a.com", summary="A"))

    assert registry.is_seen("https://a.com") is True
    assert registry.is_seen("https://never-seen.com") is False


def test_is_seen_by_normalized_title():
    """标题只差空格和标点时，也应判为"见过"（简单去重）。"""
    registry = SourceRegistry()
    registry.add(Citation(title="AI Agent 的未来！", url="https://a.com", summary="A"))

    # 标点/空格不同，但归一化后一致 → 判为见过
    assert registry.is_seen("https://other.com", "AI agent的未来") is True
    assert registry.is_seen("https://other.com", "完全不同的话题") is False


def test_items_returns_copy_and_keeps_order():
    """items() 应按编号顺序返回，且返回的是副本（外部修改不影响内部）。"""
    registry = SourceRegistry()
    registry.add(Citation(title="A", url="https://a.com", summary=""))
    registry.add(Citation(title="B", url="https://b.com", summary=""))

    items = registry.items()
    assert [c.title for c in items] == ["A", "B"]

    items.append(Citation(title="C", url="https://c.com", summary=""))
    assert len(registry) == 2  # 外部 append 不影响内部数据
