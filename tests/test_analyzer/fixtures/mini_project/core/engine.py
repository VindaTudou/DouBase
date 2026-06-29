"""核心引擎模块。"""

class Engine:
    def __init__(self):
        self._queue = []

    def process(self, data):
        result = self._transform(data)
        return self._validate(result)

    def _transform(self, data):
        return [item * 2 for item in data]

    def _validate(self, data):
        return all(isinstance(item, int) for item in data)
