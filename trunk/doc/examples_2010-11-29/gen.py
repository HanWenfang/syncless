#! /usr/bin/python2.4

def SquaresUpto(n):
  i = 1
  while i * i <= n:
    yield i * i
    i += 1

def CubesUpto(n):
  i = 1
  while i * i * i <= n:
    yield i * i * i
    i += 1

def Double(iter):
  for i in iter:
    yield 2 * i

for i in Double(CubesUpto(100)):
  print i
print list(Double(CubesUpto(100)))

def Merge(iter1, iter2):
  i1 = i2 = None
  while True:
    if iter1 is not None and i1 is None:
      try:
        i1 = iter1.next()
      except StopIteration:
        iter1 = None
    if iter2 is not None and i2 is None:
      try:
        i2 = iter2.next()
      except StopIteration:
        iter2 = None
    if i1 is None and i2 is None:
      break
    elif i2 is None or i1 < i2:
      yield i1
      i1 = None
    else:
      yield i2
      i2 = None

#: [1, 1, 4, 8, 9, 16, 25, 27, 36, 49, 64, 64, 81, 100]
print list(Merge(SquaresUpto(100), CubesUpto(100)))
