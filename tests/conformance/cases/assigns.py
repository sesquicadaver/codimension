"""Assignment forms for brief_ast T014."""

# AnnAssign / AugAssign / unpacking / chained at module level
count: int = 0
total = 0
total += 1
x, y = 1, 2
a = b = 3
first, *rest = [1, 2, 3]


class Box:
    size: int = 1
    width = height = 2
    left, right = 0, 1

    def paint(self):
        self.color = "red"
        self.x, self.y = 0, 1
        self.hits += 1
