from src.variables import register_command


class command:
    def __init__(self, name, description, function):
        self.name = name
        self.description = description
        self.function = function

    def execute(self, *args):
        return self.function(*args)