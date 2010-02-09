
class Lprng(object):
  __slots__ = ['seed']
  def __init__(self, seed=0):
    self.seed = int(seed) & 0xffffffff
  def next(self):
    """Generate a 32-bit unsigned random number."""
    # http://en.wikipedia.org/wiki/Linear_congruential_generator
    self.seed = (
        ((1664525 * self.seed) & 0xffffffff) + 1013904223) & 0xffffffff
    return self.seed
  def __iter__(self):
    return self

if __name__ == '__main__':
  for n in Lprng():
    print n
