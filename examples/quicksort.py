"""快速排序（原地版 + 稳定的函数式版）。

运行：python examples/quicksort.py
测试：python -m doctest examples/quicksort.py -v

要点
----
1. 原地版用 **Hoare 分区**：双指针从两端向中间夹，交换逆序的一对元素。
   相比 Lomuto 分区，它在元素大量相等时不会退化成 O(n^2)。
2. 基准值随机选，避免"已排序数组"这种最坏输入把递归深度打爆。
3. 递归只对**较小的一边**递归、较大的一边用 while 循环继续，
   于是递归深度上界是 O(log n)，不会栈溢出。
4. 稳定性：原地快排不稳定；需要稳定时用 faithful_quicksort。
"""

from __future__ import annotations

import random
from typing import Generator, Iterable, List, Sequence, TypeVar

T = TypeVar("T")


# ---------------------------------------------------------------- 原地版


def _partition(a: List[T], lo: int, hi: int) -> int:
    """Hoare 分区，返回右段的起始下标。

    返回 j 满足：a[lo:j] 的元素都 <= a[j:hi] 的元素。
    """
    pivot = a[random.randint(lo, hi - 1)]
    i, j = lo, hi - 1
    while True:
        while a[i] < pivot:
            i += 1
        while a[j] > pivot:
            j -= 1
        if i >= j:
            return i
        a[i], a[j] = a[j], a[i]
        i += 1
        j -= 1


def quicksort(a: List[T], lo: int = 0, hi: int | None = None) -> List[T]:
    """原地快排，返回同一个列表对象。

    >>> quicksort([])
    []
    >>> quicksort([1])
    [1]
    >>> quicksort([3, 1, 2])
    [1, 2, 3]
    >>> quicksort([2, 2, 2, 1])
    [1, 2, 2, 2]
    >>> x = [5, 4, 3, 2, 1]; quicksort(x) is x
    True
    """
    if hi is None:
        hi = len(a)
    if hi - lo < 2:
        return a
    while hi - lo > 1:
        p = _partition(a, lo, hi)
        # 先处理小的一边，大的一边交给循环 —— 保证递归深度是 O(log n)
        if p - lo < hi - p:
            quicksort(a, lo, p)
            lo = p
        else:
            quicksort(a, p, hi)
            hi = p
    return a


# ---------------------------------------------------------------- 稳定版


def faithful_quicksort(items: Iterable[T]) -> List[T]:
    """不修改入参的稳定快排（经典的"小/等/大"三段式）。

    代价是额外的内存；换来的是"相等元素保持原相对顺序"。
    """
    seq: Sequence[T] = list(items)
    return list(_sort(seq))


def _sort(seq: Sequence[T]) -> Generator[T, None, None]:
    if len(seq) <= 1:
        yield from seq
        return
    pivot = seq[len(seq) // 2]
    yield from _sort([x for x in seq if x < pivot])
    yield from (x for x in seq if x == pivot)
    yield from _sort([x for x in seq if x > pivot])


# ---------------------------------------------------------------- 演示


def _is_sorted(a: Sequence[T]) -> bool:
    return all(a[i] <= a[i + 1] for i in range(len(a) - 1))


def main() -> None:
    data = [random.randint(0, 99) for _ in range(20)]
    print("原始:", data)
    print("排序:", quicksort(list(data)))

    # 几个容易踩坑的输入
    cases = [
        [],                              # 空
        [7],                             # 单元素
        [1, 2, 3, 4, 5],                 # 已有序（快排最坏输入）
        [5, 4, 3, 2, 1],                 # 完全逆序
        [3, 3, 3, 3],                    # 全相等
        [1, 1, 2, 1, 2, 1],              # 大量重复
    ]
    for c in cases:
        got = quicksort(list(c))
        assert _is_sorted(got) and sorted(c) == got, (c, got)
    print("边界用例全部通过 ✓")

    # 稳定性：用元组第二位做标记，检查相等键的相对顺序没变
    pairs = [(1, "a"), (2, "b"), (1, "c"), (2, "d"), (1, "e")]
    stable = faithful_quicksort(pairs)          # 只比较第一个元素
    print("稳定排序:", stable)
    assert stable == [(1, "a"), (1, "c"), (1, "e"), (2, "b"), (2, "d")]
    print("稳定性检查通过 ✓")


if __name__ == "__main__":
    main()
