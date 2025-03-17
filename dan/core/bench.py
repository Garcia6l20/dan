import contextlib
import time


class BenchmarkEntry:
    def __init__(self, name, parent):
        self.name = name
        self.parent = parent
        self.t0 = None
        self.t1 = None

    def start(self):
        self.t0 = time.time()

    def end(self):
        self.t1 = time.time()

    def elapsed(self):
        return self.t1 - self.t0


class Benchmarker:
    all: list["Benchmarker"] = list()

    def __init__(self, name):
        self.name = name
        self.entries: list[BenchmarkEntry] = list()
        Benchmarker.all.append(self)

    def begin(self, name):
        e = BenchmarkEntry(name, self)
        self.entries.append(e)
        e.start()
        return e

    @contextlib.contextmanager
    def __call__(self, name):
        try:
            e = self.begin(name)
            yield e
        finally:
            e.end()


@contextlib.contextmanager
def benchmark(name):
    yield Benchmarker(name)


def report_all():
    for b in Benchmarker.all:
        for e in b.entries:
            print(f"{b.name}.{e.name}: {e.elapsed()}")
