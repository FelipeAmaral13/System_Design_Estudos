import threading
import time

EPOCH_MS = 1_700_000_000_000

NODE_ID_BITS = 10
SEQUENCE_BITS = 12

MAX_NODE_ID = (1 << NODE_ID_BITS) - 1
MAX_SEQUENCE = (1 << SEQUENCE_BITS) - 1


class SnowflakeGenerator:
    """Twitter-style Snowflake ID generator: timestamp | node_id | sequence."""

    def __init__(self, node_id: int) -> None:
        if node_id < 0 or node_id > MAX_NODE_ID:
            raise ValueError(f"node_id must be between 0 and {MAX_NODE_ID}")
        self._node_id = node_id
        self._lock = threading.Lock()
        self._last_timestamp = -1
        self._sequence = 0

    def next_id(self) -> int:
        with self._lock:
            timestamp = self._current_millis()

            if timestamp < self._last_timestamp:
                timestamp = self._last_timestamp

            if timestamp == self._last_timestamp:
                self._sequence = (self._sequence + 1) & MAX_SEQUENCE
                if self._sequence == 0:
                    timestamp = self._wait_next_millis(timestamp)
            else:
                self._sequence = 0

            self._last_timestamp = timestamp

            return (
                ((timestamp - EPOCH_MS) << (NODE_ID_BITS + SEQUENCE_BITS))
                | (self._node_id << SEQUENCE_BITS)
                | self._sequence
            )

    def _current_millis(self) -> int:
        return int(time.time() * 1000)

    def _wait_next_millis(self, current_timestamp: int) -> int:
        timestamp = self._current_millis()
        while timestamp <= current_timestamp:
            timestamp = self._current_millis()
        return timestamp
