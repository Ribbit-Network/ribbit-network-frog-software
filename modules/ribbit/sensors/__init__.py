
class Output:
    def __init__(self):
        self._outputs = []

    def add_output(self, output):
        self._outputs.append(output)

    async def write(self, sensor, data):
        for output in self._outputs:
            await output.write(sensor, data)
