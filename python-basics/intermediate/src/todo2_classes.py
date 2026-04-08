from typing import List


class Logger:
    """Stores messages in memory."""

    def __init__(self) -> None:
        self._messages: List[str] = []

    def log(self, message: str) -> None:
        self._messages.append(message)

    def messages(self) -> List[str]:
        return list(self._messages)


class Service:
    """Uses a Logger (composition) to log operations."""

    def __init__(self, name: str, factor: int, logger: Logger) -> None:
        self.name = name
        self.factor = factor
        self.logger = logger

    def handle(self, data: int) -> int:
        result = data * self.factor
        self.logger.log(
            f"svc={self.name} data={data} factor={self.factor} result={result}"
        )
        return result

    def __str__(self) -> str:
        return f"Service(name={self.name}, factor={self.factor})"
