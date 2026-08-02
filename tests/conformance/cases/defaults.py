def f(a=1, b=2):
    return a + b


def g(a, b=2, /, c=3, *, d=4, e=5):
    return a, b, c, d, e
