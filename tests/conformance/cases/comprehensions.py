nums = [x * 2 for x in range(3)]
unique = {x for x in nums}
mapping = {x: x * x for x in nums}
gen = (x for x in nums if x)
