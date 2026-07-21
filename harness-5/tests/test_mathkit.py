"""验收测试(固定,由 harness 提供,等价于"可执行的规格")。

这些用例就是验收标准:模型生成的 mathkit.py 必须让它们全绿。
verify 会把生成产物目录加入 PYTHONPATH,于是 `import mathkit` 命中的是模型产物。
"""
import unittest

import mathkit  # 由 verify 通过 PYTHONPATH 注入的模型产物


class TestMathkit(unittest.TestCase):
    def test_add(self):
        self.assertEqual(mathkit.add(2, 3), 5)
        self.assertEqual(mathkit.add(-1, 1), 0)

    def test_is_prime(self):
        self.assertFalse(mathkit.is_prime(1))
        self.assertTrue(mathkit.is_prime(2))
        self.assertFalse(mathkit.is_prime(4))
        self.assertTrue(mathkit.is_prime(13))

    def test_fib(self):
        self.assertEqual(mathkit.fib(0), 0)
        self.assertEqual(mathkit.fib(1), 1)
        self.assertEqual(mathkit.fib(7), 13)
        self.assertEqual(mathkit.fib(10), 55)

    def test_factorial(self):
        self.assertEqual(mathkit.factorial(0), 1)
        self.assertEqual(mathkit.factorial(5), 120)


if __name__ == "__main__":
    unittest.main()
